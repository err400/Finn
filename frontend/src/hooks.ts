import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
type Cached = { data: unknown; time: number }
const cache = new Map<string, Cached>()
export function clearResourceCache() { cache.clear() }
export function useResource<T>(path: string | null, pollMs=0) {
  const [revision,setRevision] = useState(0)
  const controller = useRef<AbortController | null>(null)
  const [state,setState] = useState<{ key: string | null; data?: T; loading: boolean; error: string; time?: number }>({ key:path, loading:!!path, error:'' })
  useEffect(() => {
    if (!path) { setState({key:null,loading:false,error:''}); return }
    const key=path, old=cache.get(key)
    const abort=new AbortController();controller.current=abort
    setState(s=>({key,data:old?.data as T | undefined ?? (s.key===key?s.data:undefined),loading:true,error:'',time:old?.time}))
    api<T>(key,{signal:abort.signal}).then(data=>{
      if(abort.signal.aborted)return
      const time=Date.now();cache.set(key,{data,time});setState({key,data,loading:false,error:'',time})
    }).catch(error=>{
      if(abort.signal.aborted)return
      setState(s=>({...s,loading:false,error:error instanceof Error?error.message:'Could not load this view.'}))
    })
    return ()=>abort.abort()
  },[path,revision])
  useEffect(()=>{
    if(!path||!pollMs)return
    const timer=setInterval(()=>{if(document.visibilityState==='visible')setRevision(r=>r+1)},pollMs)
    return()=>clearInterval(timer)
  },[path,pollMs])
  const setData=useCallback((data:T)=>{
    controller.current?.abort()
    const time=Date.now()
    if(path)cache.set(path,{data,time})
    setState({key:path,data,loading:false,error:'',time})
  },[path])
  const refresh=useCallback(()=>{controller.current?.abort();setRevision(r=>r+1)},[])
  const visible=state.key===path?state:{key:path,data:cache.get(path ?? '')?.data as T|undefined,loading:!!path,error:'',time:cache.get(path ?? '')?.time}
  return {...visible,refresh,setData,stale:!!visible.data&&!!visible.error}
}
