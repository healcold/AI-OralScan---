import io
import pytest
from PIL import Image
from app.image_processing import prepare_image, read_metadata

@pytest.mark.parametrize('extension,fmt', [('jpg','JPEG'),('jpeg','JPEG'),('png','PNG'),('webp','WEBP')])
def test_supported_formats_are_saved_and_retrieved(setup, extension, fmt):
    client,_,_=setup
    scan=client.post('/api/scans',json={}).json()['scan_id']
    data=io.BytesIO(); Image.new('RGB',(8,4),(10,40,200)).save(data,format=fmt)
    response=client.post(f'/api/scans/{scan}/assets',data={'source_type':'upload'},files={'file':(f'image.{extension}',data.getvalue(),'application/octet-stream')})
    assert response.status_code==201
    asset=response.json(); assert asset['metadata']['width']==8
    assert client.get(f'/api/scans/{scan}/assets/{asset["asset_id"]}/content').content==data.getvalue()

@pytest.mark.parametrize('orientation,expected', [(1,(4,2)),(2,(4,2)),(3,(4,2)),(4,(4,2)),(5,(2,4)),(6,(2,4)),(7,(2,4)),(8,(2,4))])
def test_exif_orientation_mapping_and_original_preservation(tmp_path,orientation,expected):
    path=tmp_path/'image.jpg'; image=Image.new('RGB',(4,2),(10,40,200)); exif=image.getexif();exif[274]=orientation;image.save(path,exif=exif)
    before=path.read_bytes(); tensor,transform=prepare_image(path,(8,8),color_order='BGR',dtype='float32',scale=1/255)
    assert tensor.shape==(1,3,8,8) and transform.oriented_size==expected
    assert read_metadata(path)['orientation']==orientation
    corners=[transform.input_to_raw(x,y) for x,y in [(0,0),(8,0),(0,8),(8,8)]]
    assert set(corners)=={(0,0),(4,0),(0,2),(4,2)}
    assert corners[0] == {1:(0,0),2:(4,0),3:(4,2),4:(0,2),5:(0,0),6:(0,2),7:(4,2),8:(4,0)}[orientation]
    assert path.read_bytes()==before

def test_rgb_bgr_and_invalid_configuration(tmp_path):
    path=tmp_path/'image.png';Image.new('RGB',(2,2),(10,40,200)).save(path)
    rgb,_=prepare_image(path,(2,2),color_order='RGB',dtype='uint8',scale=1)
    bgr,_=prepare_image(path,(2,2),color_order='BGR',dtype='uint8',scale=1)
    assert list(rgb[0,:,0,0])==[10,40,200] and list(bgr[0,:,0,0])==[200,40,10]
    with pytest.raises(ValueError): prepare_image(path,(0,2),color_order='RGB',dtype='uint8',scale=1)
