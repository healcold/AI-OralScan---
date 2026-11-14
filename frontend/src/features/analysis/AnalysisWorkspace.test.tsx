import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import AnalysisWorkspace from './AnalysisWorkspace'
const scan={scan_id:'s1'};const asset={asset_id:'a1',filename:'sample.png',modality:'image_2d'}
const finding={finding_id:'f1',asset_id:'a1',job_id:'j1',category:'sample',confidence:.75,location:{bbox:[1,2,7,8],image_size:[10,10]},evidence:{is_demo:false},model_version:'v1'}
beforeEach(()=>vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,status:200,json:async()=>url==='/api/models/status'?{status:'MODEL_NOT_CONFIGURED',model:null}:url==='/api/scans'?{items:[scan]}:url.endsWith('/assets')?{items:[asset]}:{jobs:[{job_id:'j1',asset_id:'a1',status:'succeeded'}],findings:[finding]}}))))
it('shows findings for the selected image and highlights a selected result',async()=>{render(<AnalysisWorkspace/>);expect(await screen.findByRole('button',{name:/sample 模型评分/})).toBeInTheDocument();expect(screen.getByText('模型未配置')).toBeInTheDocument();expect(screen.getByRole('button',{name:'分析图像'})).toBeDisabled();fireEvent.click(screen.getByRole('button',{name:/sample 模型评分/}));expect(screen.getByRole('button',{name:/sample 模型评分/})).toHaveClass('selected');fireEvent.click(screen.getByRole('button',{name:'显示原图'}));expect(screen.queryByLabelText('检测结果叠加层')).not.toBeInTheDocument();expect(screen.getByText(/不代表患病概率/)).toBeInTheDocument()})

