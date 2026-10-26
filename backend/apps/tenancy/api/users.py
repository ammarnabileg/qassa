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
            "is_active": m.is_active, "has_password": m.user.has_usable_password()}


class InviteIn(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    role = serializers.SlugField()
    all_branches = serializers.BooleanField(default=False)
    branch_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    discount_limit_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, default=0)


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
                user = User.objects.create_user(v["email"], None, full_name=v["full_name"], phone=phone,
                                                mfa_required=role.key in {"owner", "finance_manager", "accountant"})
            if Membership.objects.filter(user=user, tenant_id=request.tenant_id).exists():
                raise DomainError(code="user_already_member")
            m = Membership.objects.create(user=user, tenant_id=request.tenant_id, role=role,
                                          discount_limit_percent=v["discount_limit_percent"])
            _set_scope(m, v["all_branches"], v["branch_ids"])
            audit("users.invited", tenant_id=request.tenant_id, actor=request.user, obj=m, data={"email": user.email, "role": role.key})
        sent = accounts.deliver(user, "invite") if not user.has_usable_password() else {"channel": "existing_account"}
        return Response({**member_out(m), "delivery": sent}, status=status.HTTP_201_CREATED)


class MemberIn(serializers.Serializer):
    role = serializers.SlugField(required=False)
    all_branches = serializers.BooleanField(required=False)
    branch_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    discount_limit_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    is_active = serializers.BooleanField(required=False)


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
                m.role = role
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
        return Response({"delivery": accounts.deliver(m.user, "invite")})


def _raise(code):
    raise DomainError(code=code)
