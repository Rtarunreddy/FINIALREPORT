"""Exercise the running API and download its verified output."""
import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file', nargs='?', type=Path, default=Path(__file__).parent / 'test-assets' / 'messy-report.docx')
    parser.add_argument('--base', default='http://127.0.0.1:8000/api')
    args = parser.parse_args()
    if not args.file.exists(): raise ValueError('Run create_test_report.py first, or pass an existing DOCX path.')
    def request(path, data=None, headers=None):
        with urllib.request.urlopen(urllib.request.Request(args.base + path, data=data, headers=headers or {}), timeout=180) as response:
            return response.read()
    boundary = 'reportready' + uuid.uuid4().hex
    payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="test-report.docx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n'.encode() + args.file.read_bytes() + f'\r\n--{boundary}--\r\n'.encode())
    uploaded = json.loads(request('/uploads', payload, {'Content-Type': f'multipart/form-data; boundary={boundary}'}))
    profile = json.loads(request('/profiles'))[0]
    body = json.dumps({'profile': profile}).encode()
    audit = json.loads(request(f"/uploads/{uploaded['id']}/audit", body, {'Content-Type': 'application/json'}))
    result = json.loads(request(f"/uploads/{uploaded['id']}/apply", body, {'Content-Type': 'application/json'}))
    if result['report']['before'] != result['report']['after']: raise ValueError('Content metrics changed unexpectedly.')
    output = Path(__file__).parent / 'test-assets'; output.mkdir(exist_ok=True)
    (output / 'formatted-test.docx').write_bytes(request(f"/outputs/{result['id']}/document"))
    (output / 'pipeline-result.json').write_text(json.dumps({'audit': audit, 'result': result}, indent=2), encoding='utf-8')
    print(json.dumps(result['report']['changed'], indent=2))
    print('Passed. Formatted document and change report saved in test-assets.')


if __name__ == '__main__':
    try: main()
    except urllib.error.HTTPError as error:
        print(f'API error {error.code}: {error.read().decode()}', file=sys.stderr); sys.exit(1)
    except Exception as error:
        print(f'Test failed: {error}', file=sys.stderr); sys.exit(1)
