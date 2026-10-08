import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest'
import { createRenderer,nextTick,reactive,ssrContextKey } from 'vue'
import View from './OptimizerResultsView.vue'
const mocks=vi.hoisted(()=>({api:vi.fn(),push:vi.fn(),route:null,demo:null}))
vi.mock('vue-router',async original=>({...await original(),useRoute:()=>mocks.route,useRouter:()=>({push:mocks.push})}))
vi.mock('../stores/demoMode.js',()=>({useDemoModeStore:()=>mocks.demo}))
vi.mock('../utils/optimizerResearch.js',async original=>({...await original(),researchApi:(...args)=>mocks.api(...args)}))
vi.mock('chart.js/auto',()=>({default:class {destroy(){}}}))
const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
let app,state
async function settle(){for(let i=0;i<5;i++)await nextTick()}
function mount(){app=renderer.createApp({setup(props,ctx){state=View.setup(props,ctx);return ()=>null}});app.provide(ssrContextKey,{modules:new Set()});app.mount({})}
beforeEach(()=>{vi.useFakeTimers();mocks.api.mockReset();mocks.push.mockReset();mocks.route=reactive({params:{researchId:'first'}});mocks.demo=reactive({enabled:false})})
afterEach(()=>{app?.unmount();app=null;vi.useRealTimers()})
describe('Saved research page lifecycle',()=>{
  it('prepares a higher-precision linked request without starting another pricing job',async()=>{
    mocks.api.mockResolvedValueOnce({id:'first',status:'COMPLETED'})
    mount();await settle();state.refinePrecision(16000)
    expect(mocks.push).toHaveBeenCalledWith({path:'/structuring/optimizer',query:{from:'first',simulations:'16000'}})
    expect(mocks.api).toHaveBeenCalledTimes(1)
  })
  it('polls saved results then stops at completion; navigation never cancels the server job',async()=>{
    mocks.api.mockResolvedValueOnce({id:'first',status:'RUNNING'}).mockResolvedValueOnce({id:'first',status:'COMPLETED'})
    mount();await settle();await vi.advanceTimersByTimeAsync(2100)
    expect(state.record.value.status).toBe('COMPLETED')
    await vi.advanceTimersByTimeAsync(10000);expect(mocks.api).toHaveBeenCalledTimes(2)
    app.unmount();app=null
    expect(mocks.api.mock.calls.every(call=>call[1]==='GET')).toBe(true)
  })
  it('ignores stale responses and hides metadata as soon as demo mode is enabled',async()=>{
    let release
    mocks.api.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve})).mockResolvedValueOnce({id:'second',status:'COMPLETED',title:'Sensitive'})
    mount();mocks.route.params.researchId='second';await settle()
    release({id:'first',status:'RUNNING'});await settle()
    expect(state.record.value.id).toBe('second')
    mocks.demo.enabled=true;await settle()
    expect(state.record.value).toBeNull();await vi.advanceTimersByTimeAsync(10000)
    expect(mocks.api).toHaveBeenCalledTimes(2)
  })
  it('requests an explicit stop through the owned job endpoint',async()=>{
    mocks.api.mockResolvedValueOnce({id:'first',status:'RUNNING'}).mockResolvedValueOnce({stopping:true})
    mount();await settle();await state.cancel()
    expect(mocks.api).toHaveBeenLastCalledWith('/first/cancel','POST',{})
    expect(state.stopping.value).toBe(true)
  })
})
