/** IndexedDB for offline selling (D-013): the device credential, the catalogue snapshot, and unsent receipts. */
const DB = 'qassa-offline'
const VERSION = 1

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, VERSION)
    r.onupgradeneeded = () => {
      const db = r.result
      if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv')
      if (!db.objectStoreNames.contains('sales')) db.createObjectStore('sales', { keyPath: 'payload.uuid' })
    }
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}

async function tx<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open()
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode)
    const req = fn(t.objectStore(store))
    t.oncomplete = () => resolve(req.result)
    t.onerror = () => reject(t.error)
    t.onabort = () => reject(t.error)
  })
}

export const kvGet = <T>(key: string) => tx<T | undefined>('kv', 'readonly', (s) => s.get(key) as IDBRequest<T | undefined>)
export const kvSet = (key: string, value: unknown) => tx('kv', 'readwrite', (s) => s.put(value, key))
export const kvDel = (key: string) => tx('kv', 'readwrite', (s) => s.delete(key))

export type StoredSale = { payload: Record<string, unknown> & { uuid: string; seq: number; total: string }; signature: string; tenant: number; printed: Record<string, unknown> }
export const salesAll = () => tx<StoredSale[]>('sales', 'readonly', (s) => s.getAll() as IDBRequest<StoredSale[]>)
export const salePut = (sale: StoredSale) => tx('sales', 'readwrite', (s) => s.put(sale))
export const saleDel = (uuid: string) => tx('sales', 'readwrite', (s) => s.delete(uuid))

/** Reserve the next receipt number of this device (persisted before the receipt is shown). */
export async function nextSeq(tenant: number): Promise<number> {
  const key = `seq:${tenant}`
  const n = ((await kvGet<number>(key)) ?? 0) + 1
  await kvSet(key, n)
  return n
}
