import {useState, type ReactNode} from 'react'
import {api, setReviewerToken} from '../api'
import {clearResourceCache} from '../hooks'

export function ReviewerGate({children}:{children:ReactNode}) {
  const required=import.meta.env.VITE_REVIEWER_MODE==='true'
  const [unlocked,setUnlocked]=useState(false),[code,setCode]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('')
  async function unlock(e:React.FormEvent){
    e.preventDefault();setBusy(true);setError('');setReviewerToken(code)
    try{await api('/portfolio/overview');clearResourceCache();setCode('');setUnlocked(true)}
    catch(err){setReviewerToken('');setError(err instanceof Error?err.message:'Unable to connect')}
    finally{setBusy(false)}
  }
  function lock(){clearResourceCache();setReviewerToken('');setUnlocked(false)}
  if(!required)return <>{children}</>
  if(unlocked)return <><button className="reviewer-lock button button-small button-secondary" onClick={lock}>Lock review session</button>{children}</>
  return <main className="reviewer-gate"><form onSubmit={unlock} className="aside-block"><p className="brand">finn<span>✳</span></p><p className="eyebrow">Private ENAM review</p><h1>Evidence before inference.</h1><p>Enter the access code shared by the submitter. The portfolio is a demo and every network profile is synthetic.</p><label htmlFor="reviewer-code">Reviewer access code</label><input id="reviewer-code" type="password" autoComplete="off" required minLength={32} value={code} onChange={e=>setCode(e.target.value)} disabled={busy}/>{error&&<p role="alert">{error}</p>}<button className="button button-primary" disabled={busy}>{busy?'Connecting…':'Open FINN'}</button><p className="fine-print">The code stays in memory for this tab and clears on reload. A free backend may need time to wake up.</p></form></main>
}
