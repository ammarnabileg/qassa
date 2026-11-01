"""Company users: list, invite, change role/branches/limits, deactivate."""
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.audit.services.log import record as audit
from apps.core.errors import DomainError
from apps.identity.models import User
from apps.identity.services import accounts
from apps.tenancy.api.base import TenantAPIView
from apps.tenancy.models import Branch, Membership, MembershipBranch, Role


def member_out(m: Membership) -> dict:
    return {"id": m.id, "user_id": m.user_id, "email": m.user.email, "full_name": m.user.full_name, "phone": m.user.phone,
            "role": m.role.key, "role_name": {"ar": m.role.name_ar, "en": m.role.name_en}, "all_branches": m.all_branches,
            "branch_ids": sorted(m.branch_ids() or []), "discount_limit_percent": str(m.discount_limit_percent),
            "is_active": m.is_active, "has_password": m.user.has_usable_password(),
            "permissions": sorted(m.permissions()), "extra_permissions": sorted(m.extra_permissions or []),
            "denied_permissions": sorted(m.denied_permissions or [])}


def check_grantable(actor: Membership, codes) -> set[str]:
    """Known codes only, and nobody hands out a permission they don't have themselves (an owner has all)."""
    from apps.tenancy.permissions_catalog import ALL
    codes = set(codes)
    unknown = codes - ALL
    if unknown:
        raise DomainError(code="permission_unknown", details={"codes": sorted(unknown)})
    beyond = codes - actor.permissions()
    if beyond:
        raise DomainError(code="permission_not_yours", details={"codes": sorted(beyond)})
    return codes


class InviteIn(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    role = serializers.SlugField()
    all_branches = serializers.BooleanField(default=False)
    branch_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    discount_limit_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, default=0)
    password = serializers.CharField(required=False, allow_blank=True, default="", write_only=True, max_length=128)  # set it now instead of a link


def _set_scope(m, all_branches, branch_ids):
    if not all_branches:
        if not branch_ids:
            raise DomainError(code="branches_required")
        if Branch.objects.filter(id__in=branch_ids).count() != len(set(branch_ids)):
            raise DomainError(code="branch_unknown")
    m.all_branches = all_branches
    m.save(update_fields=["all_branches"])
    MembershipBranch.objects.filter(membership=m).delete()
    for b in ([] if all_branches else set(branch_ids)):
        MembershipBranch.objects.create(tenant_id=m.tenant_id, membership=m, branch_id=b)


class UsersView(TenantAPIView):
    required_permissions = {"GET": "users.manage", "POST": "users.manage"}

    @extend_schema(responses=dict)
    def get(self, request):
        qs = Membership.objects.filter(tenant_id=request.tenant_id).select_related("user", "role").order_by("user__full_name")
        return Response([member_out(m) for m in qs])

    @extend_schema(request=InviteIn, responses={201: dict})
    def post(self, request):
        from apps.customers.services.phone import normalize_phone
        s = InviteIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        role = Role.objects.filter(key=v["role"]).first() or _raise("role_unknown")
        if role.key == "owner" and request.membership.role.key != "owner":
            raise DomainError(code="owner_only")  # only an owner can add another owner
        phone = normalize_phone(v["phone"]) if v["phone"].strip() else ""
        with transaction.atomic():
            user = User.objects.filter(email=v["email"].lower()).first()
            if user is None:
                if v["password"]:
                    from django.contrib.auth.password_validation import validate_password
                    from django.core.exceptions import ValidationError
                    try:
                        validate_password(v["password"], User(email=v["email"], full_name=v["full_name"]))
                    except ValidationError as e:
                        raise DomainError(code="password_weak", details={"reasons": e.messages})
                user = User.objects.create_user(v["email"], v["password"] or None, full_name=v["full_name"], phone=phone,
                                                mfa_required=role.key in {"owner", "finance_manager", "accountant"})
                set_now = bool(v["password"])
            else:
                set_now = False
            if Membership.objects.filter(user=user, tenant_id=request.tenant_id).exists():
                raise DomainError(code="user_already_member")
            m = Membership.objects.create(user=user, tenant_id=request.tenant_id, role=role,
                                          discount_limit_percent=v["discount_limit_percent"])
            _set_scope(m, v["all_branches"], v["branch_ids"])
            audit("users.invited", tenant_id=request.tenant_id, actor=request.user, obj=m, data={"email": user.email, "role": role.key,
                                                                                         "password_set_by_manager": set_now})
        if set_now:
            sent = {"channel": "password_set"}   # the manager hands the password over; nothing is sent
        elif user.has_usable_password():
            sent = {"channel": "existing_account"}
        else:
            sent = accounts.deliver(user, "invite", tenant_whatsapp=True)
        return Response({**member_out(m), "delivery": sent}, status=status.HTTP_201_CREATED)


class MemberIn(serializers.Serializer):
    role = serializers.SlugField(required=False)
    all_branches = serializers.BooleanField(required=False)
    branch_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    discount_limit_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    is_active = serializers.BooleanField(required=False)
    # the full set this person should have; stored as differences from their role
    permissions = serializers.ListField(child=serializers.CharField(max_length=60), required=False)


class UserDetailView(TenantAPIView):
    required_permissions = {"PATCH": "users.manage"}

    @extend_schema(request=MemberIn, responses=dict)
    def patch(self, request, pk):
        m = get_object_or_404(Membership.objects.select_related("user", "role"), pk=pk, tenant_id=request.tenant_id)
        if m.user_id == request.user.id:
            raise DomainError(code="cannot_edit_self")
        if m.role.key == "owner" and request.membership.role.key != "owner":
            raise DomainError(code="owner_only")
        s = MemberIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        with transaction.atomic():
            if "role" in v:
                role = Role.objects.filter(key=v["role"]).first() or _raise("role_unknown")
                if role.key == "owner" and request.membership.role.key != "owner":
                    raise DomainError(code="owner_only")
                if role.id != m.role_id:
                    m.extra_permissions, m.denied_permissions = [], []   # a new role starts clean
                m.role = role
            if "permissions" in v:
                if m.role.key == "owner":
                    raise DomainError(code="owner_has_all")
                want = set(v["permissions"])
                check_grantable(request.membership, want - m.permissions())   # only what is being added must be the actor's own
                from apps.tenancy.permissions_catalog import ALL
                if want - ALL:
                    raise DomainError(code="permission_unknown", details={"codes": sorted(want - ALL)})
                base = set(m.role.permissions)
                # removing is always allowed; adding must be within the actor's own permissions (checked above)
                m.extra_permissions, m.denied_permissions = sorted(want - base), sorted(base - want)
            if "discount_limit_percent" in v:
                m.discount_limit_percent = v["discount_limit_percent"]
            if "is_active" in v:
                m.is_active = v["is_active"]
            m.save()
            if "all_branches" in v or "branch_ids" in v:
                _set_scope(m, v.get("all_branches", m.all_branches), v.get("branch_ids", list(m.branch_ids() or [])))
            audit("users.changed", tenant_id=request.tenant_id, actor=request.user, obj=m, data={k: str(x) for k, x in v.items()})
        return Response(member_out(Membership.objects.select_related("user", "role").get(id=m.id)))



class UserResendView(TenantAPIView):
    required_permissions = {"POST": "users.manage"}

    @extend_schema(request=None, responses=dict)
    def post(self, request, pk):
        """Re-send the invitation (only for users who never set a password)."""
        m = get_object_or_404(Membership.objects.select_related("user"), pk=pk, tenant_id=request.tenant_id)
        if m.user.has_usable_password():
            raise DomainError(code="already_active")
        return Response({"delivery": accounts.deliver(m.user, "invite", tenant_whatsapp=True)})


def _raise(code):
    raise DomainError(code=code)


class RoleIn(serializers.Serializer):
    name_ar = serializers.CharField(max_length=80)
    name_en = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    permissions = serializers.ListField(child=serializers.CharField(max_length=60), required=False, default=list)


def role_out(r: Role, counts: dict) -> dict:
    return {"id": r.id, "key": r.key, "name_ar": r.name_ar, "name_en": r.name_en, "permissions": sorted(r.permissions),
            "is_system": r.is_system, "editable": r.key != "owner", "members": counts.get(r.id, 0)}


class RolesView(TenantAPIView):
    """The company's roles and the permission catalogue. Owners and user managers edit them; the owner role keeps everything."""
    required_permissions = {"GET": "users.manage", "POST": "users.manage"}

    @extend_schema(responses=dict)
    def get(self, request):
        from django.db.models import Count
        from apps.tenancy.permissions_catalog import PERMISSIONS
        counts = dict(Membership.objects.filter(tenant_id=request.tenant_id, is_active=True).values("role_id")
                      .annotate(n=Count("id")).values_list("role_id", "n"))
        return Response({"roles": [role_out(r, counts) for r in Role.objects.order_by("-is_system", "id")],
                         "catalog": list(PERMISSIONS)})

    @extend_schema(request=RoleIn, responses={201: dict})
    def post(self, request):
        import uuid
        s = RoleIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        perms = check_grantable(request.membership, v["permissions"])
        r = Role.objects.create(key=f"custom-{uuid.uuid4().hex[:8]}", name_ar=v["name_ar"], name_en=v["name_en"] or v["name_ar"],
                                permissions=sorted(perms), is_system=False)
        audit("roles.created", tenant_id=request.tenant_id, actor=request.user, obj=r, data={"name": r.name_ar, "permissions": sorted(perms)})
        return Response(role_out(r, {}), status=status.HTTP_201_CREATED)


class RoleDetailView(TenantAPIView):
    required_permissions = {"PATCH": "users.manage", "DELETE": "users.manage"}

    @extend_schema(request=RoleIn, responses=dict)
    def patch(self, request, pk):
        r = get_object_or_404(Role.objects.all(), pk=pk)
        if r.key == "owner":
            raise DomainError(code="owner_has_all")
        if request.membership.role_id == r.id and request.membership.role.key != "owner":
            raise DomainError(code="cannot_edit_self")     # nobody widens or narrows their own role
        s = RoleIn(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if "permissions" in v:
            new = set(v["permissions"])
            check_grantable(request.membership, new - set(r.permissions))   # only additions need the actor to hold them
            before = sorted(r.permissions)
            r.permissions = sorted(new)
        if "name_ar" in v:
            r.name_ar = v["name_ar"]
        if v.get("name_en"):
            r.name_en = v["name_en"]
        r.save()
        audit("roles.changed", tenant_id=request.tenant_id, actor=request.user, obj=r,
              data={"name": r.name_ar, "permissions": r.permissions, **({"before": before} if "permissions" in v else {})})
        return Response(role_out(r, {}))

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        r = get_object_or_404(Role.objects.all(), pk=pk)
        if r.is_system:
            raise DomainError(code="role_is_system")
        if Membership.objects.filter(role=r).exists():
            raise DomainError(code="role_in_use")
        audit("roles.deleted", tenant_id=request.tenant_id, actor=request.user, obj=r, data={"name": r.name_ar})
        r.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
