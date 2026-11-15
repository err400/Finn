import {describe,it,expect,vi} from 'vitest'
import {render,screen,within,waitFor,fireEvent} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {App} from '../App'
import {PushView} from '../components/PushView'
import {AlertsView} from '../components/AlertsView'
import {ResearchView} from '../components/ResearchView'
import {PortfolioView} from '../components/PortfolioView'
import {useResource} from '../hooks'
import type {Overview,Rule} from '../api'
import {overview,quiet,replay,research,contact,rule,alert} from './fixtures'
function response(body:unknown,status=200){return new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json'}})}
function backend(override?:(url:URL,init?:RequestInit)=>Response|Promise<Response>|undefined){
  const requests:{url:URL;method:string;body:Record<string,unknown>|null}[]=[]
  const rules:Rule[]=[{...rule}]
  const fetch=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const url=new URL(String(input)),method=init?.method??'GET',body=init?.body?JSON.parse(String(init.body)):null
    requests.push({url,method,body})
    const custom=override?.(url,init);if(custom)return await custom
    const path=url.pathname.replace('/api/v1','')
    if(path==='/health')return response({status:'ok',providers:{llm:{configured:true,model:'synthetic-test-model'}}})
    if(path==='/portfolio/overview')return response(overview)
    if(path==='/push/refresh-status')return response({status:'idle',message:'Ready',automatic_refresh:true,interval_seconds:300})
    if(path==='/push/refresh')return response({status:'recently_checked',message:'Sources checked recently; cached records reused.'},202)
    if(path==='/push/digest')return response(['replay','all'].includes(url.searchParams.get('mode')??'')?replay:quiet)
    if(path==='/push/rules'&&method==='POST'){const saved={...body,id:rules.length+1,enabled:true} as Rule;rules.push(saved);return response(saved,201)}
    if(path==='/push/rules')return response(rules)
    if(path.startsWith('/push/rules/')&&method==='PATCH'){const r=rules.find(r=>r.id===Number(path.split('/').at(-1)))!;r.enabled=body.enabled;return response(r)}
    if(path==='/push/alerts')return response([alert])
    if(path==='/push/evaluate')return response({new_alert_count:1,skipped:[]})
    if(path.startsWith('/data/companies/')&&path.endsWith('/documents'))return response({items:[]})
    if(path==='/network/recommendations')return response({recommendations:[contact]})
    if(path==='/research'&&method==='POST')return response({...research,ticker:body.ticker,question:body.question,workflow:body.workflow},201)
    return response({detail:'Unhandled synthetic test route '+path},404)
  })
  vi.stubGlobal('fetch',fetch);return {requests,rules,fetch}
}
describe.each([{width:390,nav:'Mobile navigation'},{width:1440,nav:'Desktop navigation'}])('navigation at $width CSS pixels',({width,nav})=>{
  it('opens real portfolio detail and carries the company into research without auto-running a model',async()=>{
    Object.defineProperty(window,'innerWidth',{value:width,configurable:true})
    const user=userEvent.setup(),api=backend();render(<App/>)
    await screen.findByRole('heading',{name:'Find what deserves your attention.'})
    await user.click(within(screen.getByRole('navigation',{name:nav})).getByRole('link',{name:'Portfolio'}))
    await screen.findByRole('heading',{name:'Portfolio, in focus.'})
    await user.type(screen.getByLabelText('Search portfolio'),'RELIANCE')
    expect(screen.queryByRole('button',{name:'Open Tata Consultancy Services details'})).not.toBeInTheDocument()
    await user.click(screen.getByRole('button',{name:'Open Reliance Industries details'}))
    const dialog=await screen.findByRole('dialog')
    expect(within(dialog).getByText('₹1,500.50')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button',{name:'Research RELIANCE'}))
    await screen.findByRole('heading',{name:'Start with the evidence.'})
    expect(screen.getByLabelText('NSE ticker')).toHaveValue('RELIANCE')
    expect(api.requests.filter(r=>r.method==='POST'&&r.url.pathname.endsWith('/research'))).toHaveLength(0)
  })
})
it('keeps replay honest and connects an event to its exact source and synthetic introduction path',async()=>{
  const user=userEvent.setup();backend();render(<PushView overview={overview} onResearch={vi.fn()} onPortfolio={vi.fn()} onAlerts={vi.fn()}/>)
  await screen.findByText('No stored filings in this window')
  expect(screen.getByText('Refresh due')).toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:'Historical replay'}))
  await screen.findByRole('heading',{name:replay.important[0].title})
  expect(screen.queryByText('Refresh due')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:'Inspect evidence'}))
  const dialog=await screen.findByRole('dialog')
  expect(within(dialog).getByRole('link',{name:/Open original filing/})).toHaveAttribute('href','https://example.org/filing.pdf#page=1')
  expect(within(dialog).getByText(/time unknown/)).toBeInTheDocument()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Inspect evidence'})).toHaveFocus()
  await user.click(screen.getByRole('button',{name:'View introduction to Priya Demo Menon'}))
  expect(await screen.findByText('Second-degree connection')).toBeInTheDocument()
  expect(screen.getByText('Aarav Demo Mehta')).toBeInTheDocument()
  expect(screen.getByText(/All roles, education and personal relationships here are invented/)).toBeInTheDocument()
})
it('validates custom windows before sending requests and uses explicit IST boundaries',async()=>{
  const user=userEvent.setup(),api=backend();render(<PushView overview={overview} onResearch={vi.fn()} onPortfolio={vi.fn()} onAlerts={vi.fn()}/>)
  await screen.findByText('No stored filings in this window')
  await user.click(screen.getByRole('button',{name:'Custom'}))
  fireEvent.change(screen.getByLabelText('From · IST'),{target:{value:'2025-08-01'}})
  fireEvent.change(screen.getByLabelText('Until · exclusive'),{target:{value:'2025-07-30'}})
  const before=api.requests.length
  await user.click(screen.getByRole('button',{name:'Apply'}))
  expect(screen.getByText('End date must be after the start date.')).toBeInTheDocument()
  expect(api.requests.length).toBe(before)
  fireEvent.change(screen.getByLabelText('From · IST'),{target:{value:'2025-07-29'}})
  await user.click(screen.getByRole('button',{name:'Apply'}))
  await waitFor(()=>expect(api.requests.some(r=>r.url.searchParams.get('start')==='2025-07-29T00:00:00+05:30'&&r.url.searchParams.get('mode')==='all')).toBe(true))
  expect(await screen.findByRole('heading',{name:replay.important[0].title})).toBeInTheDocument()
  expect(screen.getByText('Historical record')).toBeInTheDocument()
})
it('saves a configured volume rule and persists a real pause through PATCH',async()=>{
  const user=userEvent.setup(),api=backend();render(<AlertsView overview={overview}/>)
  await screen.findByText('Large daily moves')
  await user.click(screen.getByRole('button',{name:'New watch rule'}))
  const d=await screen.findByRole('dialog')
  await user.selectOptions(within(d).getByLabelText('Watch for'),'volume_spike')
  await user.selectOptions(within(d).getByLabelText('Company'),'RELIANCE')
  await user.clear(within(d).getByLabelText('Volume threshold · ×'))
  await user.type(within(d).getByLabelText('Volume threshold · ×'),'2.5')
  await user.type(within(d).getByLabelText(/Rule name/),'Unusual volume')
  await user.click(within(d).getByRole('button',{name:'Save watch rule'}))
  await screen.findByText('Unusual volume')
  const post=api.requests.find(r=>r.method==='POST'&&r.url.pathname.endsWith('/rules'))!
  expect(post.body).toMatchObject({kind:'volume_spike',ticker:'RELIANCE',threshold:'2.5',lookback:20})
  const toggle=screen.getByRole('switch',{name:'Enable Unusual volume'})
  await user.click(toggle)
  await waitFor(()=>expect(toggle).toHaveAttribute('aria-checked','false'))
  expect(api.rules.find(r=>r.name==='Unusual volume')?.enabled).toBe(false)
})
it('preserves rule input and explains a failed save',async()=>{
  const user=userEvent.setup();backend((url,init)=>url.pathname.endsWith('/push/rules')&&init?.method==='POST'?response({detail:'Storage unavailable; please retry.'},503):undefined)
  render(<AlertsView overview={overview}/>);await screen.findByText('Large daily moves')
  await user.click(screen.getByRole('button',{name:'New watch rule'}))
  await user.type(screen.getByLabelText(/Rule name/),'Keep this draft')
  await user.click(screen.getByRole('button',{name:'Save watch rule'}))
  expect(await screen.findByText('Storage unavailable; please retry.')).toBeInTheDocument()
  expect(screen.getByLabelText(/Rule name/)).toHaveValue('Keep this draft')
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})
it('evaluates explicit historical data and makes trigger arithmetic inspectable',async()=>{
  const user=userEvent.setup(),api=backend();render(<AlertsView overview={overview}/>);await screen.findByText('Large daily moves')
  await user.click(screen.getByText('Check rules against stored data'))
  fireEvent.change(screen.getByLabelText('Use observations available by'),{target:{value:'2026-11-02'}})
  await user.selectOptions(screen.getByLabelText('Filing source mode'),'replay')
  await user.click(screen.getByRole('button',{name:'Evaluate enabled rules'}))
  await screen.findByRole('status')
  expect(api.requests.find(r=>r.url.pathname.endsWith('/evaluate'))?.body).toEqual({as_of:'2026-11-02',mode:'replay'})
  await user.click(screen.getByRole('button',{name:'See why this triggered'}))
  const d=await screen.findByRole('dialog')
  expect(within(d).getByText('(close / previous_close - 1) * 100')).toBeInTheDocument()
  expect(within(d).getByRole('link',{name:'Original observation 1'})).toHaveAttribute('href','https://example.org/price-observation')
})
it('renders primary-source research, calculated comparisons, citations and contextual network',async()=>{
  const user=userEvent.setup(),api=backend();render(<ResearchView companies={overview.items}/>)
  await user.click(screen.getByRole('button',{name:'Build a research brief'}))
  expect(await screen.findByRole('heading',{name:'Source-checked brief'})).toBeInTheDocument()
  expect(screen.getByText('Synthetic company operates energy and retail businesses.')).toBeInTheDocument()
  expect(screen.getByRole('link',{name:'Source · PDF page 2'})).toHaveAttribute('href','https://example.org/annual.pdf#page=2')
  await user.click(screen.getByRole('tab',{name:'Financial comparisons'}))
  expect(screen.getByText('+10.00%')).toBeInTheDocument()
  expect(screen.getByText('Unavailable')).toBeInTheDocument()
  expect(screen.queryByText('—%')).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab',{name:'Evidence (1)'}))
  expect(screen.getByRole('link',{name:'Original document · page 2'})).toHaveAttribute('href','https://example.org/annual.pdf#page=2')
  expect(screen.getByRole('button',{name:'View introduction to Priya Demo Menon'})).toBeInTheDocument()
  expect(api.requests.find(r=>r.url.pathname.endsWith('/research'))?.body).toMatchObject({ticker:'RELIANCE',workflow:'snapshot'})
})
it('handles missing primary evidence without displaying fabricated financial values',async()=>{
  const user=userEvent.setup();backend((url,init)=>url.pathname.endsWith('/research')&&init?.method==='POST'?response({...research,status:'insufficient_evidence',answer:null,evidence:[],network:[],financials:{metrics:[]},evidence_period_end:null},201):undefined)
  render(<ResearchView companies={overview.items}/>);await user.click(screen.getByRole('button',{name:'Build a research brief'}))
  await screen.findByRole('heading',{name:'Insufficient evidence'})
  expect(screen.getByText('No supported research conclusion')).toBeInTheDocument()
  await user.click(screen.getByRole('tab',{name:'Financial comparisons'}))
  expect(screen.getByText('No supported numeric comparison')).toBeInTheDocument()
  expect(screen.queryByText('100.00')).not.toBeInTheDocument()
})
it('retains previously loaded portfolio data when a refresh fails',async()=>{
  let reads=0;const user=userEvent.setup();backend(url=>url.pathname.endsWith('/portfolio/overview')?++reads===1?response(overview):response({detail:'Temporary failure'},503):undefined)
  function Harness(){const data=useResource<Overview>('/portfolio/overview');return <PortfolioView resource={data} onResearch={vi.fn()}/>}
  render(<Harness/>);await screen.findByRole('button',{name:'Open Reliance Industries details'})
  await user.click(screen.getByRole('button',{name:'Refresh view'}))
  expect(await screen.findByText('Showing the last successful result')).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Open Reliance Industries details'})).toBeInTheDocument()
  expect(screen.getByText('Temporary failure')).toBeInTheDocument()
})


it('requests a real source refresh rather than only rereading the digest',async()=>{
  const user=userEvent.setup(),api=backend();render(<PushView overview={overview} onResearch={vi.fn()} onPortfolio={vi.fn()} onAlerts={vi.fn()}/>)
  await screen.findByText('No stored filings in this window')
  await user.click(screen.getByRole('button',{name:'Refresh exchange sources'}))
  expect(await screen.findByText('Sources checked recently; cached records reused.')).toBeInTheDocument()
  expect(api.requests.some(r=>r.method==='POST'&&r.url.pathname.endsWith('/push/refresh'))).toBe(true)
  expect(api.requests.filter(r=>r.url.pathname.endsWith('/push/digest')).length).toBeGreaterThanOrEqual(2)
})

it('opens the app directly even if an obsolete reviewer flag is still set in hosting',async()=>{
  vi.stubEnv('VITE_REVIEWER_MODE','true')
  try{
    backend();render(<App/>)
    expect(await screen.findByRole('heading',{name:'Find what deserves your attention.'})).toBeInTheDocument()
    expect(screen.queryByLabelText('Reviewer access code')).not.toBeInTheDocument()
  }finally{vi.unstubAllEnvs()}
})
