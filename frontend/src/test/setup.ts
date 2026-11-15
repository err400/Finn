import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { clearResourceCache } from '../hooks'
beforeEach(()=>{clearResourceCache();window.history.replaceState(null,'','/');window.scrollTo=vi.fn()})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})
