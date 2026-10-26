import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'

/** A save action: keeps the last error for <ErrorText>, refreshes the given queries on success. */
export function useSave<T>(invalidate: (string | number)[][], onDone?: (r: T) => void) {
  const qc = useQueryClient()
  const [error, setError] = useState<unknown>(null)
  const m = useMutation({
    mutationFn: (req: { path: string; method?: string; body?: unknown; idempotencyKey?: string }) =>
      api<T>(req.path, { method: req.method ?? 'POST', body: req.body, idempotencyKey: req.idempotencyKey }),
    onMutate: () => setError(null),
    onError: (e) => setError(e),
    onSuccess: (r) => { invalidate.forEach((k) => qc.invalidateQueries({ queryKey: k })); onDone?.(r) },
  })
  return { save: m.mutate, busy: m.isPending, error, reset: () => setError(null) }
}
