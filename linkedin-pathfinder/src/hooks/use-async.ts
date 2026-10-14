import { useCallback, useEffect, useRef, useState } from "react"

/** Run an async loader when its deps change; exposes data, error, loading and reload(). */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: Error; loading: boolean }>({ loading: true })
  const fnRef = useRef(fn)
  fnRef.current = fn
  const run = useCallback(() => {
    let live = true
    setState((s) => ({ ...s, loading: true }))
    fnRef.current().then(
      (data) => live && setState({ data, loading: false }),
      (error: Error) => live && setState({ error, loading: false })
    )
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(run, [run])
  return { ...state, reload: run }
}
