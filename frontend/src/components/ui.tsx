import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
export type IconName='briefing'|'portfolio'|'research'|'alerts'|'arrow'|'external'|'refresh'|'close'|'people'|'chevron'|'plus'|'check'|'source'|'search'|'filter'
const paths:Record<IconName,ReactNode>={
  briefing:<><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h4"/></>,portfolio:<><rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V3h8v4M3 12h18M10 12v3h4v-3"/></>,research:<><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6M10 7v6"/></>,alerts:<><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M9 21h6"/></>,arrow:<path d="M4 12h16m-6-6 6 6-6 6"/>,external:<><path d="M14 3h7v7m0-7L10 14M10 3H4v17h17v-6"/></>,refresh:<><path d="M20 7v5h-5M4 17v-5h5M19 7a8 8 0 0 0-13-2M5 17a8 8 0 0 0 13 2"/></>,close:<path d="m6 6 12 12M6 18 18 6"/>,people:<><circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 5v2"/></>,chevron:<path d="m9 5 7 7-7 7"/>,plus:<path d="M12 4v16M4 12h16"/>,check:<path d="m4 12 5 5L20 6"/>,source:<><path d="M5 3h10l4 4v14H5zM14 3v5h5M8 12h8M8 16h6"/></>,search:<><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></>,filter:<path d="M3 5h18M6 12h12M9 19h6"/>
}
export function Icon({name,size=18}:{name:IconName;size?:number}) {return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>}
export function Badge({children,tone='neutral'}:{children:ReactNode;tone?:'neutral'|'green'|'amber'|'red'}) {return <span className={`badge badge-${tone}`}>{children}</span>}
export function EmptyState({title,children,action}:{title:string;children:ReactNode;action?:ReactNode}) {return <div className="empty-state"><span className="empty-mark"><Icon name="source" size={24}/></span><h3>{title}</h3><p>{children}</p>{action&&<div className="mt-5">{action}</div>}</div>}
export function ErrorNotice({children,onRetry,stale=false}:{children:ReactNode;onRetry?:()=>void;stale?:boolean}) {return <div className="notice notice-error" role="alert"><div><strong>{stale?'Showing the last successful result':'Couldn’t update this view'}</strong><p>{children}</p></div>{onRetry&&<button className="button button-small button-secondary" onClick={onRetry}>Retry</button>}</div>}
export function Skeleton({rows=3}:{rows?:number}) {return <div className="skeleton-stack" role="status" aria-label="Loading data">{Array.from({length:rows},(_,i)=><div key={i} className="skeleton"><span/><span/><span/></div>)}</div>}
export function SourceLink({url,children}:{url:string|null|undefined;children:ReactNode}) {return url?<a className="source-link" href={url} target="_blank" rel="noreferrer">{children}<Icon name="external" size={13}/></a>:<span className="muted text-sm">Source unavailable</span>}
const dialogStack:string[]=[]
let originalOverflow=''
export function Drawer({title,eyebrow,children,onClose}:{title:string;eyebrow?:string;children:ReactNode;onClose:()=>void}) {
  const panel=useRef<HTMLDivElement>(null),id=useId(),close=useRef(onClose);close.current=onClose
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null
    if(!dialogStack.length)originalOverflow=document.body.style.overflow
    dialogStack.push(id)
    document.body.style.overflow='hidden';panel.current?.querySelector<HTMLButtonElement>('button')?.focus()
    function handle(e:KeyboardEvent){if(dialogStack.at(-1)!==id)return;if(e.key==='Escape'){e.preventDefault();close.current()}
      if(e.key==='Tab'){const items=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex="0"]')??[]).filter(el=>!el.closest('[hidden]')&&(!el.closest('details:not([open])')||el.tagName==='SUMMARY'));const first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}}
    document.addEventListener('keydown',handle)
    return()=>{const index=dialogStack.indexOf(id);if(index>=0)dialogStack.splice(index,1);if(!dialogStack.length)document.body.style.overflow=originalOverflow;document.removeEventListener('keydown',handle);if(previous?.isConnected)previous.focus()}
  },[])
  return createPortal(<div className="drawer-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><div ref={panel} className="drawer" role="dialog" aria-modal="true" aria-labelledby={id}><header className="drawer-header"><div>{eyebrow&&<p className="eyebrow">{eyebrow}</p>}<h2 id={id}>{title}</h2></div><button className="icon-button" aria-label="Close panel" onClick={onClose}><Icon name="close"/></button></header><div className="drawer-content">{children}</div></div></div>,document.body)
}
