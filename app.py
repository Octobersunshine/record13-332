import re
import json
import multiprocessing
import queue
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

DEFAULT_TIMEOUT = 3
MAX_TEXT_LENGTH = 100000

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>正则表达式测试工具</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 20px; max-width: 1000px; margin: 0 auto; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; margin-bottom: 20px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #555; }
        input[type="text"], textarea, select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; font-family: 'Courier New', monospace; }
        textarea { min-height: 120px; resize: vertical; }
        .flags { display: flex; gap: 15px; flex-wrap: wrap; }
        .flag-item { display: flex; align-items: center; gap: 5px; }
        button { background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; transition: background 0.3s; }
        button:hover { background: #0056b3; }
        .results { margin-top: 30px; }
        .result-item { background: #f8f9fa; padding: 15px; border-radius: 4px; margin-bottom: 10px; border-left: 4px solid #007bff; }
        .match { background: #fff3cd; padding: 2px 4px; border-radius: 2px; }
        .group { background: #d4edda; padding: 2px 4px; border-radius: 2px; margin-left: 10px; }
        .error { background: #f8d7da; color: #721c24; padding: 15px; border-radius: 4px; border-left: 4px solid #dc3545; }
        .highlight { background: #ffeeba; }
        pre { background: #f8f9fa; padding: 15px; border-radius: 4px; overflow-x: auto; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>正则表达式测试工具</h1>
        <form id="regexForm">
            <div class="form-group">
                <label for="pattern">正则表达式</label>
                <input type="text" id="pattern" name="pattern" placeholder="例如: \d+ 或 ([a-z]+)" required>
            </div>
            <div class="form-group">
                <label for="flags">匹配标志</label>
                <div class="flags">
                    <label class="flag-item"><input type="checkbox" name="flags" value="IGNORECASE"> IGNORECASE (忽略大小写)</label>
                    <label class="flag-item"><input type="checkbox" name="flags" value="MULTILINE"> MULTILINE (多行模式)</label>
                    <label class="flag-item"><input type="checkbox" name="flags" value="DOTALL"> DOTALL (点号匹配换行)</label>
                    <label class="flag-item"><input type="checkbox" name="flags" value="UNICODE"> UNICODE</label>
                    <label class="flag-item"><input type="checkbox" name="flags" value="VERBOSE"> VERBOSE (详细模式)</label>
                </div>
            </div>
            <div class="form-group">
                <label for="test_text">测试文本</label>
                <textarea id="test_text" name="test_text" placeholder="输入要测试的文本..." required></textarea>
            </div>
            <div class="form-group">
                <label for="method">匹配方法</label>
                <select id="method" name="method">
                    <option value="findall">findall (查找所有匹配)</option>
                    <option value="search">search (查找第一个匹配)</option>
                    <option value="match">match (从开头匹配)</option>
                    <option value="fullmatch">fullmatch (完全匹配)</option>
                    <option value="finditer">finditer (迭代器模式)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="timeout">超时时间（秒，0.5-10）</label>
                <input type="number" id="timeout" name="timeout" value="3" min="0.5" max="10" step="0.5">
            </div>
            <button type="submit">测试匹配</button>
        </form>
        
        <div class="results" id="results"></div>
    </div>

    <script>
        document.getElementById('regexForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            const flags = [];
            formData.getAll('flags').forEach(f => flags.push(f));
            
            const data = {
                pattern: formData.get('pattern'),
                test_text: formData.get('test_text'),
                flags: flags,
                method: formData.get('method'),
                timeout: parseFloat(formData.get('timeout')) || 3
            };
            
            try {
                const response = await fetch('/api/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                displayResults(result, data.test_text);
            } catch (error) {
                document.getElementById('results').innerHTML = 
                    '<div class="error">请求失败: ' + error.message + '</div>';
            }
        });
        
        function displayResults(result, testText) {
            const container = document.getElementById('results');
            
            if (result.error) {
                container.innerHTML = '<div class="error"><strong>错误:</strong> ' + result.error + '</div>';
                return;
            }
            
            let html = '<h2>匹配结果</h2>';
            html += '<p><strong>匹配方法:</strong> ' + result.method + '</p>';
            html += '<p><strong>匹配数量:</strong> ' + result.match_count + '</p>';
            
            if (result.match_count > 0) {
                html += '<h3>详细匹配信息:</h3>';
                result.matches.forEach((match, idx) => {
                    html += '<div class="result-item">';
                    html += '<strong>匹配 #' + (idx + 1) + ':</strong> ';
                    html += '<span class="match">' + escapeHtml(match.match) + '</span>';
                    html += ' <small>(位置: ' + match.start + '-' + match.end + ')</small>';
                    
                    if (match.groups && match.groups.length > 0) {
                        html += '<br><strong>捕获组:</strong>';
                        match.groups.forEach((g, gIdx) => {
                            html += ' <span class="group">组' + (gIdx + 1) + ': ' + escapeHtml(g || '(空)') + '</span>';
                        });
                    }
                    
                    if (match.groupdict && Object.keys(match.groupdict).length > 0) {
                        html += '<br><strong>命名捕获组:</strong>';
                        for (const [key, value] of Object.entries(match.groupdict)) {
                            html += ' <span class="group">' + key + ': ' + escapeHtml(value || '(空)') + '</span>';
                        }
                    }
                    html += '</div>';
                });
                
                html += '<h3>高亮显示:</h3>';
                html += '<pre>' + highlightMatches(testText, result.matches) + '</pre>';
            } else {
                html += '<div class="result-item" style="border-left-color: #dc3545;">没有找到匹配</div>';
            }
            
            html += '<h3>原始响应:</h3>';
            html += '<pre>' + escapeHtml(JSON.stringify(result, null, 2)) + '</pre>';
            
            container.innerHTML = html;
        }
        
        function highlightMatches(text, matches) {
            let result = '';
            let lastEnd = 0;
            
            const sortedMatches = [...matches].sort((a, b) => a.start - b.start);
            
            for (const match of sortedMatches) {
                result += escapeHtml(text.substring(lastEnd, match.start));
                result += '<span class="highlight">' + escapeHtml(text.substring(match.start, match.end)) + '</span>';
                lastEnd = match.end;
            }
            
            result += escapeHtml(text.substring(lastEnd));
            return result;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""

def _regex_worker(pattern, test_text, flags, method, result_queue):
    try:
        compiled = re.compile(pattern, flags)
        matches = []

        if method in ('findall', 'finditer'):
            for m in compiled.finditer(test_text):
                matches.append(format_match(m))
        elif method == 'search':
            m = compiled.search(test_text)
            if m:
                matches.append(format_match(m))
        elif method == 'match':
            m = compiled.match(test_text)
            if m:
                matches.append(format_match(m))
        elif method == 'fullmatch':
            m = compiled.fullmatch(test_text)
            if m:
                matches.append(format_match(m))
        else:
            result_queue.put({'error': f'不支持的方法: {method}'})
            return

        result_queue.put({'success': True, 'matches': matches})
    except re.error as e:
        result_queue.put({'error': f'正则表达式语法错误: {str(e)}'})
    except Exception as e:
        result_queue.put({'error': f'匹配异常: {str(e)}'})


def run_regex_with_timeout(pattern, test_text, flags, method, timeout=DEFAULT_TIMEOUT):
    ctx = multiprocessing.get_context('spawn')
    result_queue = ctx.Queue()
    proc = ctx.Process(
        target=_regex_worker,
        args=(pattern, test_text, flags, method, result_queue)
    )
    proc.start()
    proc.join(timeout)

    if proc.is_alive():
        proc.terminate()
        proc.join(1)
        if proc.is_alive():
            proc.kill()
        return {'error': f'正则匹配超时（超过 {timeout} 秒），可能存在灾难性回溯，已强制终止'}

    try:
        result = result_queue.get_nowait()
        return result
    except queue.Empty:
        return {'error': '正则匹配未返回结果'}


def parse_flags(flags_list):
    flags = 0
    flag_map = {
        'IGNORECASE': re.IGNORECASE,
        'MULTILINE': re.MULTILINE,
        'DOTALL': re.DOTALL,
        'UNICODE': re.UNICODE,
        'VERBOSE': re.VERBOSE,
        'ASCII': re.ASCII,
    }
    for f in flags_list or []:
        if f in flag_map:
            flags |= flag_map[f]
    return flags

def format_match(match_obj):
    groups = match_obj.groups()
    groupdict = match_obj.groupdict()
    
    return {
        'match': match_obj.group(),
        'start': match_obj.start(),
        'end': match_obj.end(),
        'groups': [g for g in groups],
        'groupdict': {k: v for k, v in groupdict.items()}
    }

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/test', methods=['POST'])
def test_regex():
    try:
        data = request.get_json()

        pattern = data.get('pattern', '')
        test_text = data.get('test_text', '')
        flags_list = data.get('flags', [])
        method = data.get('method', 'findall')
        timeout = min(max(float(data.get('timeout', DEFAULT_TIMEOUT)), 0.5), 10)

        if not pattern:
            return jsonify({'error': '正则表达式不能为空'}), 400
        if not test_text:
            return jsonify({'error': '测试文本不能为空'}), 400
        if len(test_text) > MAX_TEXT_LENGTH:
            return jsonify({'error': f'测试文本过长（超过 {MAX_TEXT_LENGTH} 字符）'}), 400

        flags = parse_flags(flags_list)

        try:
            re.compile(pattern, flags)
        except re.error as e:
            return jsonify({'error': f'正则表达式语法错误: {str(e)}'}), 400

        result = run_regex_with_timeout(pattern, test_text, flags, method, timeout)

        if 'error' in result:
            return jsonify({'error': result['error']}), 400

        matches = result.get('matches', [])

        return jsonify({
            'success': True,
            'pattern': pattern,
            'method': method,
            'flags': flags_list,
            'test_text': test_text,
            'match_count': len(matches),
            'matches': matches,
            'timeout_seconds': timeout
        })

    except ValueError as e:
        return jsonify({'error': f'参数错误: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5001)
