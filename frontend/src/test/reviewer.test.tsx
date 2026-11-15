import {afterEach,describe,it,expect,vi} from 'vitest'
import {render,screen} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {ReviewerGate} from '../components/ReviewerGate'
import {setReviewerToken} from '../api'

afterEach(()=>{vi.unstubAllEnvs();setReviewerToken('')})
describe('private reviewer session',()=>{
 it('keeps the access code out of storage and clears it on lock',async()=>{
  vi.stubEnv('VITE_REVIEWER_MODE','true');const user=userEvent.setup()
  const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({items:[]})))
  vi.stubGlobal('fetch',fetch)
  render(<ReviewerGate><p>Private workspace</p></ReviewerGate>)
  expect(screen.queryByText('Private workspace')).not.toBeInTheDocument()
  await user.type(screen.getByLabelText('Reviewer access code'),'x'.repeat(32))
  await user.click(screen.getByRole('button',{name:'Open FINN'}))
  expect(await screen.findByText('Private workspace')).toBeInTheDocument()
  expect(new Headers(fetch.mock.calls[0][1].headers).get('authorization')).toBe('Bearer '+'x'.repeat(32))
  expect(sessionStorage.length).toBe(0);expect(localStorage.length).toBe(0)
  await user.click(screen.getByRole('button',{name:'Lock review session'}))
  expect(screen.getByLabelText('Reviewer access code')).toHaveValue('')
  expect(screen.queryByText('Private workspace')).not.toBeInTheDocument()
 })
 it('preserves the gate on failed authentication',async()=>{
  vi.stubEnv('VITE_REVIEWER_MODE','true');const user=userEvent.setup()
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Enter the private reviewer access code'}),{status:401})))
  render(<ReviewerGate><p>Private workspace</p></ReviewerGate>)
  await user.type(screen.getByLabelText('Reviewer access code'),'x'.repeat(32))
  await user.click(screen.getByRole('button',{name:'Open FINN'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Enter the private reviewer access code')
  expect(screen.queryByText('Private workspace')).not.toBeInTheDocument()
 })
})
