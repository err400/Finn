export function dateLabel(value: string | null | undefined, withYear=true) {
  if(!value)return 'Not available'
  const d=new Date(value.length===10?value+'T12:00:00+05:30':value)
  if(Number.isNaN(d.getTime()))return 'Date unavailable'
  return new Intl.DateTimeFormat('en-IN',{day:'numeric',month:'short',...(withYear?{year:'numeric' as const}:{}),timeZone:'Asia/Kolkata'}).format(d)
}
export function timeLabel(value: string | null | undefined) {
  if(!value)return 'Not recorded'
  const d=new Date(value)
  if(Number.isNaN(d.getTime()))return 'Time unavailable'
  return new Intl.DateTimeFormat('en-IN',{day:'numeric',month:'short',hour:'numeric',minute:'2-digit',timeZone:'Asia/Kolkata'}).format(d)+' IST'
}
export function priceLabel(value: string | null | undefined) {
  if(value==null || value==='' || !Number.isFinite(Number(value)))return '—'
  return new Intl.NumberFormat('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value))
}
export function signed(value: string | null | undefined, suffix='%') {
  if(value==null || value==='' || !Number.isFinite(Number(value)))return 'Unavailable'
  return `${Number(value)>0?'+':''}${priceLabel(value)}${suffix}`
}
export function tone(value: string | null | undefined) { return value==null?'muted':Number(value)>0?'positive':Number(value)<0?'negative':'muted' }
export function human(value:string) { return value==='M&A'?'M&A':value.replaceAll('_',' ').replace(/^./,s=>s.toUpperCase()) }
export function sourceHost(url:string) { try{return new URL(url).hostname.replace(/^www\./,'')}catch{return 'Original source'} }
export function isHistorical(day:string|null|undefined,now=new Date()) { return !!day && now.getTime()-new Date(day+'T12:00:00+05:30').getTime()>5*86400000 }
export function istBoundary(day:string) { if(!/^\d{4}-\d{2}-\d{2}$/.test(day))throw new Error('Choose valid start and end dates.');return day+'T00:00:00+05:30' }
