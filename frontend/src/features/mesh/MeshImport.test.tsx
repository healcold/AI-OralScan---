import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import MeshImport from './MeshImport'
beforeEach(()=>vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[]})})))
it('rejects an unsupported file and disables import',()=>{const {container}=render(<MeshImport/>);fireEvent.change(container.querySelector('input[type=file]')!,{target:{files:[new File(['x'],'bad.png')]}});expect(screen.getByRole('alert')).toHaveTextContent('请选择 STL、OBJ 或 PLY');expect(screen.getByRole('button',{name:'验证并导入'})).toBeDisabled()})
it('rejects files over the size limit',()=>{const {container}=render(<MeshImport/>);const file=new File(['x'],'large.obj');Object.defineProperty(file,'size',{value:25*1024*1024+1});fireEvent.change(container.querySelector('input[type=file]')!,{target:{files:[file]}});expect(screen.getByRole('alert')).toHaveTextContent('25 MiB')})

