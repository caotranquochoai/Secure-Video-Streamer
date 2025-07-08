import os
import getpass
import struct
import requests
import time
import sys
import re
import hashlib
import json
import uuid
from flask import Flask, Response, abort, request, redirect, url_for, jsonify, render_template
from Crypto.Cipher import AES
from video import decrypt_name, CHUNK_SIZE

app = Flask(__name__)

# --- Cấu hình và Biến toàn cục ---
PASSWORD = "" # Mật khẩu của admin
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_ENCRYPTED_FOLDER = os.path.join(BASE_DIR, "output")
CACHE_FOLDER = os.path.join(BASE_DIR, "cache")
MANIFEST_FILE = os.path.join(BASE_DIR, "info_manifest.json")
DEBUG_MODE = False
AES_BLOCK_SIZE = 16
USER_SESSIONS = {} 

# --- Các hàm phụ trợ ---

def read_manifest():
    if not os.path.exists(MANIFEST_FILE): return {}
    try:
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return {}

def write_manifest(data):
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

def get_decryption_cipher(key, nonce, start_byte=0):
    key32 = key.encode("utf-8").ljust(32, b'\0')[:32]
    initial_counter_val = (start_byte // AES_BLOCK_SIZE)
    return AES.new(key32, AES.MODE_CTR, nonce=nonce, initial_value=initial_counter_val)

def generate_decrypted_chunks(data_stream, cipher, start_byte, end_byte):
    bytes_yielded = 0
    total_to_yield = end_byte - start_byte + 1
    offset_in_first_block = start_byte % AES_BLOCK_SIZE
    first_chunk_data = data_stream.read(CHUNK_SIZE)
    if not first_chunk_data: return
    decrypted_chunk = cipher.decrypt(first_chunk_data)
    actual_chunk = decrypted_chunk[offset_in_first_block:]
    bytes_to_yield = min(len(actual_chunk), total_to_yield)
    yield actual_chunk[:bytes_to_yield]
    bytes_yielded += bytes_to_yield
    while bytes_yielded < total_to_yield:
        chunk = data_stream.read(CHUNK_SIZE)
        if not chunk: break
        decrypted_chunk = cipher.decrypt(chunk)
        bytes_to_yield = min(len(decrypted_chunk), total_to_yield - bytes_yielded)
        yield decrypted_chunk[:bytes_to_yield]
        bytes_yielded += bytes_to_yield

# --- Các Endpoint Chính ---

@app.route('/stream/<filename>')
def stream_local_video(filename):
    return stream_video_handler(filename, PASSWORD)

@app.route('/stream_token/<token>')
def stream_user_video(token):
    session_data = USER_SESSIONS.get(token)
    if not session_data: abort(404, "Token không hợp lệ hoặc đã hết hạn.")
    filename = session_data['filename']
    password = session_data['password']
    return stream_video_handler(filename, password)

def stream_video_handler(filename, password):
    file_path = os.path.join(CACHE_FOLDER, filename)
    if not os.path.exists(file_path):
        file_path = os.path.join(USER_ENCRYPTED_FOLDER, filename)
        if not os.path.exists(file_path): abort(404)

    with open(file_path, 'rb') as f:
        _nonce = f.read(8)
        total_size = struct.unpack('Q', f.read(8))[0]

    range_header = request.headers.get('Range', None)
    
    def content_generator(start_byte=0, end_byte=None):
        if end_byte is None: end_byte = total_size - 1
        with open(file_path, 'rb') as f:
            nonce = f.read(8)
            _ = f.read(8)
            name_len = struct.unpack('H', f.read(2))[0]
            metadata_size = 8 + 8 + 2 + name_len
            read_start_offset = metadata_size + (start_byte // AES_BLOCK_SIZE) * AES_BLOCK_SIZE
            f.seek(read_start_offset)
            cipher = get_decryption_cipher(password, nonce, start_byte=start_byte)
            yield from generate_decrypted_chunks(f, cipher, start_byte, end_byte)

    if not range_header:
        resp = Response(content_generator(), mimetype='video/mp4', status=200)
        resp.headers.add('Content-Length', str(total_size))
        resp.headers.add('Accept-Ranges', 'bytes')
        return resp
    else:
        start_byte, end_byte = 0, None
        m = re.search(r'(\d+)-(\d*)', range_header)
        if m:
            start_byte = int(m.group(1))
            end_str = m.group(2)
            if end_str: end_byte = int(end_str)
        if end_byte is None or end_byte >= total_size: end_byte = total_size - 1
        content_length = (end_byte - start_byte) + 1
        resp = Response(content_generator(start_byte, end_byte), mimetype='video/mp4', status=206)
        resp.headers.add('Content-Range', f'bytes {start_byte}-{end_byte}/{total_size}')
        resp.headers.add('Content-Length', str(content_length))
        return resp

# --- Các Endpoint cho Người dùng ---

@app.route('/viewer')
def viewer_page():
    return render_template('viewer.html')

@app.route('/api/request_stream', methods=['POST'])
def request_stream():
    data = request.get_json()
    video_url = data.get('url')
    password = data.get('password')
    if not video_url or not password:
        return jsonify({'error': 'Thiếu URL hoặc mật khẩu.'}), 400

    url_hash = hashlib.sha1(video_url.encode('utf-8')).hexdigest()
    cached_filename = f"{url_hash}.vcc"
    cached_filepath = os.path.join(CACHE_FOLDER, cached_filename)
    manifest_data = read_manifest()

    if not os.path.exists(cached_filepath):
        print(f"📥 Người dùng yêu cầu tệp mới. Tải xuống từ: {video_url}")
        try:
            r = requests.get(video_url, stream=True)
            r.raise_for_status()
            with open(cached_filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
            print(f"✅ Tải xuống hoàn tất. Đã lưu vào: {cached_filepath}")

            print(f"🔍 Quét tên gốc cho tệp mới tải về...")
            with open(cached_filepath, 'rb') as f:
                _ = f.read(8)
                _ = f.read(8)
                name_len = struct.unpack('H', f.read(2))[0]
                encrypted_name = f.read(name_len)
                key32 = password.encode("utf-8").ljust(32, b'\0')[:32]
                original_name = decrypt_name(encrypted_name, key32)
            
            manifest_data[cached_filename] = {
                "url": video_url, "timestamp": time.time(),
                "source": "cache", "original_name": original_name
            }
            write_manifest(manifest_data)
            print(f"📝 Đã cập nhật manifest với tên gốc: {original_name}")

        except Exception as e:
            if os.path.exists(cached_filepath): os.remove(cached_filepath)
            return jsonify({'error': f'Không thể xử lý tệp từ URL: {e}'}), 500

    token = str(uuid.uuid4())
    USER_SESSIONS[token] = {'filename': cached_filename, 'password': password}
    stream_url = url_for('stream_user_video', token=token, _external=True)
    return jsonify({'stream_url': stream_url})

# --- Giao diện Quản lý ---

@app.route('/manage')
def manage_cache_page():
    return render_template('index.html')

@app.route('/api/cache', methods=['GET'])
def get_cache_files():
    manifest_data = read_manifest()
    files_info = []
    for filename, data in list(manifest_data.items()):
        source = data.get('source')
        if source == 'cache': filepath = os.path.join(CACHE_FOLDER, filename)
        elif source == 'local': filepath = os.path.join(USER_ENCRYPTED_FOLDER, filename)
        else: continue
        if os.path.exists(filepath):
            files_info.append({
                'name': filename, 'size': os.path.getsize(filepath),
                'url': data.get('url', '-'), 'timestamp': data.get('timestamp', 0),
                'original_name': data.get('original_name', 'Chưa quét'), 'source': source
            })
        else: del manifest_data[filename]
    write_manifest(manifest_data)
    return jsonify(files_info)

@app.route('/api/scan_local_files', methods=['POST'])
def scan_local_files():
    """Quét thư mục cục bộ và cập nhật manifest với tên gốc cho các tệp mới hoặc chưa được quét."""
    if not os.path.isdir(USER_ENCRYPTED_FOLDER):
        return jsonify({'error': f'Thư mục cục bộ {USER_ENCRYPTED_FOLDER} chưa được tạo.'}), 400

    manifest_data = read_manifest()
    files_updated = 0
    
    for filename in os.listdir(USER_ENCRYPTED_FOLDER):
        if not filename.endswith('.vcc'):
            continue

        entry = manifest_data.get(filename)
        # SỬA LỖI: Quét nếu tệp chưa có trong manifest, hoặc đã có nhưng chưa có tên gốc.
        if not entry or entry.get('original_name') == 'Chưa quét':
            filepath = os.path.join(USER_ENCRYPTED_FOLDER, filename)
            try:
                print(f"🔍 Đang quét tệp cục bộ: {filename}")
                with open(filepath, 'rb') as f:
                    _ = f.read(8)
                    _ = f.read(8)
                    name_len = struct.unpack('H', f.read(2))[0]
                    encrypted_name = f.read(name_len)
                    key32 = PASSWORD.encode("utf-8").ljust(32, b'\0')[:32]
                    original_name = decrypt_name(encrypted_name, key32)
                    
                    manifest_data[filename] = {
                        "original_name": original_name,
                        "source": "local",
                        "timestamp": os.path.getmtime(filepath),
                        "url": "-"
                    }
                    files_updated += 1
            except Exception as e:
                print(f"❌ Lỗi khi quét tệp {filename}: {e}")

    write_manifest(manifest_data)
    return jsonify({'message': f'Quét hoàn tất. Đã cập nhật thông tin cho {files_updated} tệp.'})

@app.route('/api/cache/delete/<filename>', methods=['DELETE'])
def delete_cache_file(filename):
    if '..' in filename or filename.startswith('/'):
        return jsonify({'error': 'Tên tệp không hợp lệ'}), 400
    manifest_data = read_manifest()
    file_data = manifest_data.get(filename)
    if not file_data: return jsonify({'error': 'Không tìm thấy tệp trong manifest.'}), 404
    source = file_data.get('source')
    if source == 'cache': filepath = os.path.join(CACHE_FOLDER, filename)
    elif source == 'local': filepath = os.path.join(USER_ENCRYPTED_FOLDER, filename)
    else: return jsonify({'error': 'Nguồn tệp không xác định.'}), 500
    del manifest_data[filename]
    write_manifest(manifest_data)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            return jsonify({'message': f'Đã xóa tệp {filename} thành công.'})
        except OSError as e: return jsonify({'error': f'Không thể xóa tệp: {e}'}), 500
    return jsonify({'message': f'Đã xóa mục nhập của tệp {filename} khỏi manifest.'})

# --- Hàm Main ---

def main():
    global PASSWORD
    if '--debug' in sys.argv:
        DEBUG_MODE = True
        print("🐞 Chế độ gỡ lỗi đã được bật.")
    for folder in [CACHE_FOLDER, USER_ENCRYPTED_FOLDER]:
        if not os.path.exists(folder):
            print(f"📁 Tạo thư mục cần thiết tại: {folder}")
            os.makedirs(folder)
    PASSWORD = getpass.getpass("🔑 Nhập mật khẩu ADMIN để quản lý và quét tệp cục bộ: ")
    print("\n✅ Máy chủ đã sẵn sàng!")
    print(f"✨ Giao diện quản lý có tại: http://127.0.0.1:5000/manage")
    print(f"✨ Trang cho người dùng có tại: http://127.0.0.1:5000/viewer")
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    main()