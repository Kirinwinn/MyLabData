from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, abort, Response
import pandas as pd
import os
import json as _json
import markdown
import io
import queue
import subprocess
import platform
import sys
import threading
import time
from pathlib import Path

# Ensure project root is on the import path so sibling packages resolve
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from Database.Wet.Wet_Pipeline import WET_DB_PATH, get_wet_smiles_map, run_wet_pipeline
from Database.Dry import run_dry_pipeline_refresh
from Search.Wet_ViewMode import (
    get_connection as repo_get_connection,
    get_file_path,
    get_file_record,
    list_batches_by_molecule,
    list_files_by_batch,
    list_molecules_with_types,
)
from Search.Wet_CompareMode import (
    SOLVENT_OPTIONS,
    extract_dynamic_e_series_from_pdata_files,
    extract_dynamic_fin_series_from_sdata_files,
    extract_dynamic_mtt_series_from_pdata_files,
    extract_dynamic_selectivei_series_from_pdata_files,
    extract_dynamic_uvstable_series_from_pdata_files,
    extract_e_meta_from_sdata_markdowns,
    extract_number_table_from_sdata_markdowns,
    get_compare_init_payload,
    get_batches_for_molecule,
)

# Dry ViewMode imports
from Search.Dry_ViewMode import (
    list_dry_batches,
    get_dry_batch_by_code,
    get_dry_batch_stats,
    get_all_batches_stats,
    get_trait_distribution_simple,
    get_molecules_by_trait_range,
    get_trait_info,
    get_prediction_status,
)

# Dry CompareMode imports
from Search.Dry_CompareMode import (
    search_molecule as dry_search_molecule,
    get_trait_categories_with_values,
    package_molecule_data,
)

# Dry SearchMode imports
from Search.Dry_SearchMode import (
    list_all_batches as search_list_all_batches,
    filter_molecules as search_filter_molecules,
    get_filtered_distribution,
    get_filtered_molecules_by_range,
    package_filtered_results,
)

# Dry Prediction imports
from Database.Tools.Dry.Dry_Prediction import (
    ACTIVE_MODELS as PRED_ACTIVE_MODELS,
    get_available_solvents as pred_get_solvents,
    get_model_result_info as pred_get_result_info,
    get_prediction_distribution as pred_get_distribution,
    get_prediction_molecules_by_range as pred_get_molecules_by_range,
    scan_all_prediction_availability as pred_scan_all,
)

try:
    from rdkit import Chem
    from rdkit.Chem import Draw
    RDKIT_AVAILABLE = True
    RDKIT_ERROR = None
except ImportError as e:
    RDKIT_AVAILABLE = False
    RDKIT_ERROR = str(e)
    print(f"Warning: RDKit not installed. Structure generation disabled. Error: {e}")

app = Flask(__name__)
DB_PATH = WET_DB_PATH
STRUCTURES_DIR = BASE_DIR / 'Supporting' / 'structures'
AUTO_REFRESH_ON_STARTUP = os.getenv('APP_AUTO_REFRESH_ON_STARTUP', '0') == '1'
PRELOAD_STRUCTURES_ON_STARTUP = os.getenv('APP_PRELOAD_STRUCTURES_ON_STARTUP', '0') == '1'
APP_DEBUG = os.getenv('APP_DEBUG', '0') == '1'
APP_PORT = int(os.getenv('APP_PORT', '8501'))
_REFRESH_LOCK = threading.Lock()
_DRY_REFRESH_LOCK = threading.Lock()

def get_connection():
    return repo_get_connection(DB_PATH)

def safe_read_csv(path):
    try:
        return pd.read_csv(path, encoding='utf-8')
    except UnicodeDecodeError:
        try:
            return pd.read_csv(path, encoding='gbk')
        except:
            return pd.read_csv(path, encoding='utf-8', errors='replace')

STATUS_MAP = {
    'Normal': {'class': 'normal', 'icon': 'folder'},
    'UnDone': {'class': 'undone', 'icon': 'folder'},
    'UnValuable': {'class': 'unvaluable', 'icon': 'folder'},
    'Test': {'class': 'test', 'icon': 'folder'}
}

COMPARE_PLACEHOLDER_MESSAGE = 'CompareMode backend placeholder. Rebuild in progress.'

def generate_static_structure(molecule_name, smiles):
    """
    Generates a static PNG for the molecule if it doesn't exist.
    Returns the web-accessible path to the image.
    """
    if not RDKIT_AVAILABLE or not smiles:
        return None
        
    filename = f"{molecule_name}.svg"
    # Ensure directory exists
    folder = str(STRUCTURES_DIR)
    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
        except Exception as e:
            print(f"Error creating structure folder: {e}")
            return None
        
    filepath = os.path.join(folder, filename)
    
    # Generate if missing
    if not os.path.exists(filepath):
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                # Use MolDraw2DSVG to generate SVG (doesn't require Cairo)
                try:
                    from rdkit.Chem.Draw import rdMolDraw2D
                    drawer = rdMolDraw2D.MolDraw2DSVG(600, 300)
                    drawer.DrawMolecule(mol)
                    drawer.FinishDrawing()
                    svg = drawer.GetDrawingText()
                    with open(filepath, 'w') as f:
                        f.write(svg)
                except ImportError:
                     # Fallback to old SVG method if available or fail
                     return None
            else:
                return None
        except Exception as e:
            print(f"Error drawing molecule {molecule_name}: {e}")
            return None
            
    return f"/supporting/structures/{filename}"


@app.route('/supporting/structures/<path:filename>')
def serve_supporting_structure(filename):
    return send_from_directory(str(STRUCTURES_DIR), filename)

def get_smiles_map():
    return get_wet_smiles_map()

def preload_structure_images():
    """Ensure all molecule images are generated on startup."""
    try:
        print("Initializing: Checking molecule structure images...")
        s_map = get_smiles_map()
        if not s_map:
            print("No SMILES data found to generate images.")
            return

        count = 0
        for name, smiles in s_map.items():
            # generate_static_structure checks existence internally, so this is safe to call
            res = generate_static_structure(name, smiles)
            if res:
                count += 1
        print(f"Structure images check finished. Verified {count} molecules.")
    except Exception as e:
        print(f"Error during structure image preloading: {e}")

# Keep startup fast by default; enable preload explicitly with env var.
if PRELOAD_STRUCTURES_ON_STARTUP:
    threading.Thread(target=preload_structure_images, daemon=True).start()

@app.route('/')
def index():
    # Sidebar data: molecules
    molecules = list_molecules_with_types()
    
    # Main content data
    selected_molecule = request.args.get('molecule')
    selected_exp_type = request.args.get('exp_type')
    sort_mode = request.args.get('sort', 'time')
    
    batches_data = []
    active_smiles = None  # Store SMILES for selected molecule
    structure_image_url = None  # Path to static image

    if selected_molecule:
        # Load SMILES
        smiles_map = get_smiles_map()
        active_smiles = smiles_map.get(selected_molecule)

        # Generate or fetch static image
        if active_smiles:
            structure_image_url = generate_static_structure(selected_molecule, active_smiles)

        batch_rows = list_batches_by_molecule(
            molecule=selected_molecule,
            exp_type=selected_exp_type,
            sort_mode=sort_mode,
        )
        
        for batch in batch_rows:
            b_dict = dict(batch)
            status_info = STATUS_MAP.get(b_dict.get('status', 'Normal'), STATUS_MAP['Normal'])
            b_dict['status_class'] = status_info['class']
            b_dict['status_icon'] = status_info['icon']
            
            # Display formatting
            b_dict['exp_type_display'] = b_dict.get('exp_type', '')

            # Round display: clean up "Xth_Time" -> "Xth"
            raw_round = str(b_dict.get('round', ''))
            if raw_round and raw_round.lower().endswith('_time'):
               b_dict['round_display'] = raw_round[:-5]
            else:
               b_dict['round_display'] = raw_round
            
            # Load files
            files_rows = list_files_by_batch(b_dict['id'])
            b_dict['files'] = {'RData': [], 'PData': [], 'SData': []}
            
            for f in files_rows:
                cat = f['category']
                if cat in b_dict['files']:
                    b_dict['files'][cat].append(dict(f))
            
            batches_data.append(b_dict)
    
    return render_template('index.html', 
                           molecules=molecules,
                           selected_molecule=selected_molecule,
                           selected_exp_type=selected_exp_type,
                           current_sort=sort_mode,
                           batches=batches_data,
                           active_smiles=active_smiles,
                           structure_image_url=structure_image_url,
                           rdkit_available=RDKIT_AVAILABLE,
                           rdkit_error=RDKIT_ERROR)

@app.route('/download_structure_file/<molecule_name>')
def download_structure_file(molecule_name):
    # Try SVG first (Supporting folder)
    svg_filename = f"{molecule_name}.svg"
    svg_path = str(STRUCTURES_DIR / svg_filename)
    
    if os.path.exists(svg_path):
        return send_file(svg_path, as_attachment=True, download_name=svg_filename)
        
    # Try dynamic generation of SVG if needed (High Res not really applicable to SVG but clean vector)
    if RDKIT_AVAILABLE:
        smiles_map = get_smiles_map()
        smiles = smiles_map.get(molecule_name)
        if smiles:
             try:
                 mol = Chem.MolFromSmiles(smiles)
                 if mol:
                     from rdkit.Chem.Draw import rdMolDraw2D
                     drawer = rdMolDraw2D.MolDraw2DSVG(800, 600) # Slightly larger for download
                     drawer.DrawMolecule(mol)
                     drawer.FinishDrawing()
                     svg = drawer.GetDrawingText()
                     
                     return send_file(
                         io.BytesIO(svg.encode('utf-8')),
                         mimetype='image/svg+xml',
                         as_attachment=True,
                         download_name=f"{molecule_name}.svg"
                     )
             except:
                 pass

    # Fallback/Fail
    return "Structure file not found", 404
    # Fallback/Fail
    return "Structure file not found", 404

@app.route('/reveal/<int:file_id>')
def reveal_file(file_id):
    file_path = get_file_path(file_id)

    if not file_path or not os.path.exists(file_path):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
        
    path = os.path.abspath(file_path)
    system_name = platform.system()
    
    try:
        if system_name == 'Windows':
            subprocess.run(['explorer', '/select,', path])
        elif system_name == 'Darwin': # macOS
            subprocess.run(['open', '-R', path])
        else: # Linux
            # Try to detect WSL
            is_wsl = False
            try:
                with open('/proc/version', 'r') as f:
                    if 'microsoft' in f.read().lower():
                        is_wsl = True
            except:
                pass
            
            if is_wsl:
                # Use wslpath to convert path
                p = subprocess.run(['wslpath', '-w', path], stdout=subprocess.PIPE, text=True)
                if p.returncode == 0:
                    win_path = p.stdout.strip()
                    subprocess.run(['explorer.exe', '/select,', win_path])
                else:
                    raise Exception("Failed to convert path via wslpath")
            else:
                # Standard Linux
                folder = os.path.dirname(path)
                subprocess.run(['xdg-open', folder])
            
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/refresh', methods=['POST'])
def refresh():
    if not _REFRESH_LOCK.acquire(blocking=False):
        return jsonify({'status': 'busy', 'message': 'Refresh is already running.'}), 409

    start_time = time.time()
    try:
        run_wet_pipeline()
        return jsonify({'status': 'success', 'elapsed_seconds': round(time.time() - start_time, 3)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        _REFRESH_LOCK.release()


@app.route('/refresh/dry', methods=['POST'])
def refresh_dry():
    if not _DRY_REFRESH_LOCK.acquire(blocking=False):
        return jsonify({'status': 'busy', 'message': 'Dry refresh is already running.'}), 409

    try:
        result = run_dry_pipeline_refresh()
        # Append prediction scan
        result['prediction'] = pred_scan_all()
        http_status = int(result.pop('http_status', 200))
        if result.get('status') == 'error' and http_status == 200:
            http_status = 500
        return jsonify(result), http_status
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        _DRY_REFRESH_LOCK.release()


@app.route('/refresh/dry/stream')
def refresh_dry_stream():
    """SSE endpoint streaming real-time progress of the Dry pipeline refresh."""
    if not _DRY_REFRESH_LOCK.acquire(blocking=False):
        def _busy():
            yield 'data: ' + _json.dumps({'type': 'error', 'message': 'Dry refresh is already running.'}) + '\n\n'
        return Response(_busy(), mimetype='text/event-stream')

    q: queue.Queue = queue.Queue()

    def _progress_cb(phase, batch, step, state, detail):
        q.put({'type': 'progress', 'phase': phase, 'batch': batch,
               'step': step, 'state': state, 'detail': detail})

    def _run():
        try:
            result = run_dry_pipeline_refresh(progress_callback=_progress_cb)
            # Prediction scan phase
            pred_result = pred_scan_all(progress_callback=_progress_cb)
            result['prediction'] = pred_result
            q.put({'type': 'done', 'result': result})
        except Exception as exc:
            q.put({'type': 'error', 'message': str(exc)})
        finally:
            _DRY_REFRESH_LOCK.release()

    threading.Thread(target=_run, daemon=True).start()

    def _generate():
        while True:
            try:
                msg = q.get(timeout=30)
            except queue.Empty:
                # Send SSE comment as keepalive (ignored by EventSource)
                yield ': keepalive\n\n'
                continue
            yield 'data: ' + _json.dumps(msg, default=str) + '\n\n'
            if msg.get('type') in ('done', 'error'):
                return

    return Response(_generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/serve_file/<int:file_id>')
def serve_file(file_id):
    file_path = get_file_path(file_id)

    if not file_path or not os.path.exists(file_path):
        abort(404)
        
    return send_file(file_path)

@app.route('/preview/<int:file_id>')
def preview(file_id):
    file_row = get_file_record(file_id)
    
    if not file_row:
        return "File not found in DB"
        
    filepath = file_row['filepath']
    filename = file_row['filename']
    ext = os.path.splitext(filename)[1].lower()
    
    # Debug log
    print(f"DEBUG: Previewing file_id={file_id}, path={filepath}, ext={ext}")

    if not os.path.exists(filepath):
        print(f"ERROR: File path does not exist: {filepath}")
        return "<div class='alert alert-danger'>File not found on disk</div>"
        
    try:
        content_html = ""
        
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
            # Using flex to vertically and horizontally center the image
            content_html = f'''
            <div class="h-100 d-flex flex-column">
                <div class="p-2 border-bottom d-flex justify-content-between align-items-center bg-light">
                    <span class="fw-bold text-truncate">{filename}</span>
                    <a href="./serve_file/{file_id}" target="_blank" class="btn btn-sm btn-primary-material" download>
                        <i class="fas fa-download me-1"></i> Download
                    </a>
                </div>
                <div class="flex-grow-1 d-flex justify-content-center align-items-center p-3" style="overflow: auto;">
                    <img src="./serve_file/{file_id}" style="max-height: 90%; max-width: 100%; object-fit: contain;">
                </div>
            </div>
            '''
            
        elif ext == '.csv':
            df = safe_read_csv(filepath)
            
            table_html = df.to_html(index=False, classes='custom-table', border=0)
            
            # Normal: Header with buttons + Table
            content_html = f'''
            <div class="d-flex flex-column h-100">
                <div class="p-2 border-bottom d-flex justify-content-between align-items-center bg-light">
                    <div class="d-flex gap-2">
                            <a href="./serve_file/{file_id}" class="btn btn-sm btn-outline-primary rounded-pill" download title="Download CSV"><i class="fas fa-download"></i></a>
                            <span class="fw-bold align-self-center">{filename}</span>
                    </div>
                </div>
                <div class="flex-grow-1 p-2" style="overflow: hidden;">
                    <div class="custom-table-container">{table_html}</div>
                </div>
            </div>
            '''
            
        elif ext in ['.xlsx', '.xls']:
            try:
                # Need openpyxl for xlsx and xlrd for xls (usually)
                xls = pd.ExcelFile(filepath)
                sheet_names = xls.sheet_names
                
                current_sheet = request.args.get('sheet')
                if not current_sheet or current_sheet not in sheet_names:
                    current_sheet = sheet_names[0]
                
                df = pd.read_excel(filepath, sheet_name=current_sheet)
                table_html = df.to_html(index=False, classes='custom-table', border=0)
                
                # Sheet selector logic
                selector_html = ""
                options = ""
                if len(sheet_names) > 0:
                    for s in sheet_names:
                        selected = "selected" if s == current_sheet else ""
                        options += f'<option value="{s}" {selected}>{s}</option>'
                
                sheet_dd = ""
                if len(sheet_names) > 1:
                    sheet_dd = f'<select class="form-select form-select-sm w-auto d-inline-block" onchange="changeSheet({file_id}, this)">{options}</select>'
                
                content_html = f'''
                <div class="d-flex flex-column h-100">
                    <div class="p-2 border-bottom d-flex justify-content-between align-items-center bg-light">
                        <div class="d-flex align-items-center gap-2">
                            <a href="./serve_file/{file_id}" class="btn btn-sm btn-outline-primary rounded-pill" download title="Download Excel"><i class="fas fa-download"></i></a>
                            {sheet_dd}
                            <span class="fw-bold small text-muted ms-1">{filename}</span>
                        </div>
                    </div>
                    <div class="flex-grow-1 p-2" style="overflow: hidden;">
                            <div class="custom-table-container">{table_html}</div>
                    </div>
                </div>
                '''

            except Exception as e:
                # Add check for openpyxl
                if "openpyxl" in str(e):
                     content_html = f"<div class='alert alert-warning'>Error: 'openpyxl' library not installed. Please run `pip install openpyxl`. Details: {e}</div>"
                else:
                     content_html = f"<div class='alert alert-warning'>Error reading Excel: {e}</div>"
                
        elif ext == '.md':
            with open(filepath, 'r', encoding='utf-8') as f:
                md_content = f.read()
            html = markdown.markdown(md_content, extensions=['tables', 'fenced_code', 'codehilite'])
            
            content_html = f'''
            <div class="h-100 d-flex flex-column">
                <div class="p-2 border-bottom d-flex justify-content-end bg-light">
                     <a href="./serve_file/{file_id}" target="_blank" class="btn btn-sm btn-primary-material" download>
                        <i class="fas fa-download me-1"></i> Download
                    </a>
                </div>
                <div class="flex-grow-1 p-3 markdown-body" style="overflow: auto; max-width: none; width: 100%; box-sizing: border-box;">
                    {html}
                </div>
            </div>
            <style>
              #preview-panel .markdown-body {{
                max-width: none !important;
                width: 100% !important;
                box-sizing: border-box;
              }}
              #preview-panel .markdown-body table {{
                display: table !important;
                width: 100% !important;
                max-width: 100% !important;
                border-collapse: collapse !important;
                overflow: visible !important;
              }}
              #preview-panel .markdown-body table th,
              #preview-panel .markdown-body table td {{
                padding: 8px 16px;
                border: 1px solid #d0d7de;
              }}
            </style>
            '''
            
        elif ext == '.txt' or ext == '.log':
             with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
             content_html = f'<div class="h-100 d-flex flex-column"><div class="p-2 border-bottom text-end"><a href="./serve_file/{file_id}" class="btn btn-sm btn-primary-material" download>Download</a></div><pre class="p-3 bg-light border flex-grow-1" style="overflow:auto;">{text}</pre></div>'
             
        elif ext == '.spc':
             content_html = f'''
             <div class="d-flex flex-column align-items-center justify-content-center h-100 text-muted">
                <i class="fas fa-file-waveform display-4 mb-3"></i>
                <h5>SPC Spectrum File</h5>
                <p>Preview not supported for this file type.</p>
                <a href="./serve_file/{file_id}" target="_blank" class="btn btn-primary-material btn-sm">Download File</a>
             </div>
             '''

        else:
            content_html = f'''
             <div class="d-flex flex-column align-items-center justify-content-center h-100 text-muted">
                <i class="far fa-file-alt display-4 mb-3"></i>
                <h5>{ext} File</h5>
                <p>Preview not available for this file type.</p>
                <a href="./serve_file/{file_id}" target="_blank" class="btn btn-primary-material btn-sm">Download File</a>
             </div>
             '''
            
        return content_html
        
    except Exception as e:
        import traceback
        traceback.print_exc() # Print full stack trace to server console
        return f"<div class='alert alert-danger'>Error generating preview: {e}</div>"


@app.route('/api/compare', methods=['GET', 'POST'])
def api_compare_placeholder():
    return jsonify({
        'ok': False,
        'placeholder': True,
        'message': COMPARE_PLACEHOLDER_MESSAGE
    }), 501


@app.route('/api/compare/wet/init', methods=['GET'])
def api_compare_wet_init():
    try:
        payload = get_compare_init_payload()
        return jsonify({'ok': True, 'payload': payload})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/compare/wet/batches', methods=['GET'])
def api_compare_wet_batches():
    molecule = (request.args.get('molecule') or '').strip()
    type_value = (request.args.get('type') or request.args.get('exp_type') or 'solventscom').strip().lower()
    if not molecule:
        return jsonify({'ok': False, 'message': 'molecule is required'}), 400

    try:
        batches = get_batches_for_molecule(molecule, type_value)
        return jsonify({'ok': True, 'molecule': molecule, 'type': type_value, 'batches': batches})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/compare/wet/sdata', methods=['GET'])
def api_compare_wet_sdata():
    raw_batch_id = (request.args.get('batch_id') or '').strip()
    type_value = (request.args.get('type') or request.args.get('exp_type') or 'solventscom').strip().lower()
    if not raw_batch_id:
        return jsonify({'ok': False, 'message': 'batch_id is required'}), 400

    try:
        batch_id = int(raw_batch_id)
    except ValueError:
        return jsonify({'ok': False, 'message': 'batch_id must be integer'}), 400

    try:
        files_rows = list_files_by_batch(batch_id)
        sdata_files = [
            f for f in files_rows
            if str(f.get('category') or '').strip().lower() == 'sdata'
        ]

        markdown_items = []
        image_items = []
        markdown_records = []

        for item in sdata_files:
            filename = str(item.get('filename') or '')
            ext = os.path.splitext(filename)[1].lower()
            file_id = int(item.get('id'))
            file_path = str(item.get('filepath') or '')

            if ext == '.md':
                md_content = ''
                if file_path and os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        md_content = f.read()
                markdown_items.append({
                    'file_id': file_id,
                    'filename': filename,
                    'text': md_content,
                })
                markdown_records.append({'filename': filename, 'text': md_content})
            elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp']:
                img_payload = {
                    'file_id': file_id,
                    'filename': filename,
                    'url': f'./serve_file/{file_id}',
                }
                image_items.append(img_payload)

        dynamic_meta = {}

        if type_value in ('fluostable', 'uvstable', 'mtt', 'e', 'selectivei'):
            number_rows = []
        else:
            number_rows = extract_number_table_from_sdata_markdowns(markdown_records, SOLVENT_OPTIONS)

        if type_value == 'uvstable':
            dynamic_series = extract_dynamic_uvstable_series_from_pdata_files(files_rows)
        elif type_value == 'mtt':
            dynamic_series = extract_dynamic_mtt_series_from_pdata_files(files_rows)
        elif type_value == 'selectivei':
            dynamic_series = extract_dynamic_selectivei_series_from_pdata_files(files_rows)
        elif type_value == 'e':
            dynamic_series = extract_dynamic_e_series_from_pdata_files(files_rows)
            dynamic_meta = extract_e_meta_from_sdata_markdowns(markdown_records)
        else:
            dynamic_series = extract_dynamic_fin_series_from_sdata_files(files_rows)

        return jsonify({
            'ok': True,
            'batch_id': batch_id,
            'type': type_value,
            'markdown': markdown_items,
            'images': image_items,
            'number_rows': number_rows,
            'dynamic_series': dynamic_series,
            'dynamic_meta': dynamic_meta,
        })
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
#  DRY VIEWMODE API - 占位数据（待后续实现）
# ═══════════════════════════════════════════════════════════════════


@app.route('/api/dry/batches', methods=['GET'])
def api_dry_batches():
    """Get list of all Dry batches from Dry.db."""
    try:
        batches = list_dry_batches()
        return jsonify({'ok': True, 'batches': batches})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/batch/<batch_code>', methods=['GET'])
def api_dry_batch_info(batch_code):
    """Get info for a specific batch."""
    try:
        batch = get_dry_batch_by_code(batch_code)
        if not batch:
            return jsonify({'ok': False, 'message': 'Batch not found'}), 404
        return jsonify({'ok': True, 'batch': batch})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/batch/<batch_code>/stats', methods=['GET'])
def api_dry_batch_stats(batch_code):
    """Get statistics for a batch."""
    try:
        if batch_code == 'All':
            stats = get_all_batches_stats()
        else:
            stats = get_dry_batch_stats(batch_code)
        if 'error' in stats:
            return jsonify({'ok': False, 'message': stats['error']}), 404
        return jsonify({'ok': True, 'stats': stats})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/distribution', methods=['GET'])
def api_dry_distribution():
    """Get trait value distribution for a batch from Property parquet."""
    batch_code = request.args.get('batch', '').strip()
    trait = request.args.get('trait', '').strip()
    bins_count = int(request.args.get('bins', 20))

    if not batch_code:
        return jsonify({'ok': False, 'message': 'batch is required'}), 400
    if not trait:
        return jsonify({'ok': False, 'message': 'trait is required'}), 400

    try:
        distribution = get_trait_distribution_simple(batch_code, trait, bins_count)
        if 'error' in distribution:
            return jsonify({'ok': False, 'message': distribution['error']}), 404
        return jsonify({'ok': True, 'distribution': distribution})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/molecules_by_range', methods=['GET'])
def api_dry_molecules_by_range():
    """Get molecules within a trait value range from Property parquet."""
    batch_code = request.args.get('batch', '').strip()
    trait = request.args.get('trait', '').strip()
    min_val = request.args.get('min', type=float)
    max_val = request.args.get('max', type=float)
    limit = request.args.get('limit', 100, type=int)

    if not batch_code or not trait or min_val is None or max_val is None:
        return jsonify({'ok': False, 'message': 'batch, trait, min, max are required'}), 400

    try:
        result = get_molecules_by_trait_range(batch_code, trait, min_val, max_val, limit)
        if 'error' in result:
            return jsonify({'ok': False, 'message': result['error']}), 404
        return jsonify({'ok': True, 'molecules': result['molecules'], 'total_in_range': result['total_in_range']})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/trait_info', methods=['GET'])
def api_dry_trait_info():
    """Get trait metadata for UI rendering."""
    try:
        info = get_trait_info()
        return jsonify({'ok': True, 'info': info})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/prediction_status/<batch_code>', methods=['GET'])
def api_dry_prediction_status(batch_code):
    """Get prediction model availability for a batch."""
    try:
        status = get_prediction_status(batch_code)
        return jsonify({'ok': True, 'status': status.get('models', {})})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/prediction/solvents/<batch_code>', methods=['GET'])
def api_dry_pred_solvents(batch_code):
    """Get available solvents for Proby in a batch."""
    try:
        solvents = pred_get_solvents(batch_code)
        return jsonify({'ok': True, 'solvents': solvents})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/prediction/result_info/<model>', methods=['GET'])
def api_dry_pred_result_info(model):
    """Get result column definitions for a model."""
    try:
        info = pred_get_result_info(model)
        return jsonify({'ok': True, 'info': info})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/prediction/distribution', methods=['GET'])
def api_dry_pred_distribution():
    """Get distribution of a prediction metric."""
    batch_code = request.args.get('batch', '').strip()
    model = request.args.get('model', '').strip()
    metric = request.args.get('metric', '').strip()
    solvent = request.args.get('solvent', '').strip() or None
    bins_count = int(request.args.get('bins', 50))

    if not batch_code or not model or not metric:
        return jsonify({'ok': False, 'message': 'batch, model, metric required'}), 400

    try:
        dist = pred_get_distribution(batch_code, model, metric, solvent, bins_count)
        if 'error' in dist:
            return jsonify({'ok': False, 'message': dist['error']}), 404
        return jsonify({'ok': True, 'distribution': dist})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/prediction/molecules_by_range', methods=['GET'])
def api_dry_pred_molecules_by_range():
    """Get molecules within a prediction metric range."""
    batch_code = request.args.get('batch', '').strip()
    model = request.args.get('model', '').strip()
    metric = request.args.get('metric', '').strip()
    solvent = request.args.get('solvent', '').strip() or None
    min_val = request.args.get('min', type=float)
    max_val = request.args.get('max', type=float)
    limit = request.args.get('limit', 100, type=int)

    if not batch_code or not model or not metric or min_val is None or max_val is None:
        return jsonify({'ok': False, 'message': 'batch, model, metric, min, max required'}), 400

    try:
        result = pred_get_molecules_by_range(batch_code, model, metric, min_val, max_val, solvent, limit)
        if 'error' in result:
            return jsonify({'ok': False, 'message': result['error']}), 404
        return jsonify({'ok': True, 'molecules': result['molecules'], 'total_in_range': result['total_in_range']})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
#  DRY SEARCHMODE API
# ═══════════════════════════════════════════════════════════════════


@app.route('/api/dry/search/batches', methods=['GET'])
def api_dry_search_batches():
    """List batches for Scope selector."""
    try:
        batches = search_list_all_batches()
        return jsonify({'ok': True, 'batches': batches})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/search/filter', methods=['POST'])
def api_dry_search_filter():
    """Apply filter conditions and return stats."""
    data = request.get_json(force=True)
    batch_codes = data.get('batch_codes', [])
    conditions = data.get('conditions', {})

    try:
        result = search_filter_molecules(batch_codes, conditions)
        return jsonify({'ok': True, 'stats': result})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/search/distribution', methods=['POST'])
def api_dry_search_distribution():
    """Get trait distribution for filtered molecules."""
    data = request.get_json(force=True)
    batch_codes = data.get('batch_codes', [])
    conditions = data.get('conditions', {})
    trait = data.get('trait', '')
    bins_count = data.get('bins', 50)

    if not trait:
        return jsonify({'ok': False, 'message': 'trait is required'}), 400

    try:
        dist = get_filtered_distribution(batch_codes, conditions, trait, bins_count)
        if 'error' in dist:
            return jsonify({'ok': False, 'message': dist['error']}), 404
        return jsonify({'ok': True, 'distribution': dist})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/search/molecules_by_range', methods=['POST'])
def api_dry_search_molecules_by_range():
    """Get molecules in a trait range from filtered set."""
    data = request.get_json(force=True)
    batch_codes = data.get('batch_codes', [])
    conditions = data.get('conditions', {})
    trait = data.get('trait', '')
    min_val = data.get('min')
    max_val = data.get('max')
    limit = data.get('limit', 100)

    if not trait or min_val is None or max_val is None:
        return jsonify({'ok': False, 'message': 'trait, min, max are required'}), 400

    try:
        result = get_filtered_molecules_by_range(
            batch_codes, conditions, trait, float(min_val), float(max_val), limit
        )
        if 'error' in result:
            return jsonify({'ok': False, 'message': result['error']}), 404
        return jsonify({'ok': True, 'molecules': result['molecules'],
                        'total_in_range': result['total_in_range']})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/search/download', methods=['POST'])
def api_dry_search_download():
    """Download filtered results as zip."""
    data = request.get_json(force=True)
    batch_codes = data.get('batch_codes', [])
    conditions = data.get('conditions', {})

    try:
        buf = package_filtered_results(batch_codes, conditions)
        return send_file(buf, mimetype='application/zip',
                         as_attachment=True, download_name='filtered_molecules.zip')
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════
#  DRY COMPAREMODE API
# ═══════════════════════════════════════════════════════════════════


@app.route('/api/dry/compare/search', methods=['GET'])
def api_dry_compare_search():
    """Search molecule by LabID or SMILES for CompareMode."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'ok': False, 'message': 'q is required'}), 400

    try:
        result = dry_search_molecule(query)
        if result is None:
            return jsonify({'ok': False, 'message': 'Molecule not found'}), 404

        # Organize traits into categories for display
        result['trait_categories'] = get_trait_categories_with_values(result['traits'])
        return jsonify({'ok': True, 'molecule': result})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/compare/download', methods=['GET'])
def api_dry_compare_download():
    """Download zip package for a molecule (traits CSV + 2D SVG + 3D SDF)."""
    lab_id = request.args.get('lab_id', '').strip()
    smiles = request.args.get('smiles', '').strip()
    if not lab_id or not smiles:
        return jsonify({'ok': False, 'message': 'lab_id and smiles are required'}), 400

    try:
        # Search to get traits
        mol_data = dry_search_molecule(lab_id)
        traits = mol_data['traits'] if mol_data else {}

        buf = package_molecule_data(lab_id, smiles, traits)

        # Add 2D SVG and 3D SDF if RDKit available
        if RDKIT_AVAILABLE:
            import zipfile
            from rdkit.Chem import AllChem
            from rdkit.Chem.Draw import rdMolDraw2D

            mol = Chem.MolFromSmiles(smiles)
            if mol:
                with zipfile.ZipFile(buf, 'a', zipfile.ZIP_DEFLATED) as zf:
                    # 2D SVG
                    drawer = rdMolDraw2D.MolDraw2DSVG(800, 600)
                    drawer.DrawMolecule(mol)
                    drawer.FinishDrawing()
                    zf.writestr(f'{lab_id}_2d.svg', drawer.GetDrawingText())

                    # 3D SDF
                    mol3d = Chem.AddHs(mol)
                    res = AllChem.EmbedMolecule(mol3d, randomSeed=42)
                    if res == -1:
                        params = AllChem.ETKDGv3()
                        params.randomSeed = 42
                        params.useRandomCoords = True
                        res = AllChem.EmbedMolecule(mol3d, params)
                    if res != -1:
                        try:
                            AllChem.MMFFOptimizeMolecule(mol3d, maxIters=500)
                        except Exception:
                            pass
                        zf.writestr(f'{lab_id}_3d.sdf', Chem.MolToMolBlock(mol3d))

                buf.seek(0)

        return send_file(
            buf,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{lab_id}_data.zip'
        )
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/dry/molecule_2d', methods=['GET'])
def api_dry_molecule_2d():
    """Generate 2D SVG for a SMILES string (real-time, no file storage)."""
    smiles = request.args.get('smiles', '').strip()
    if not smiles:
        return jsonify({'ok': False, 'message': 'smiles is required'}), 400

    if not RDKIT_AVAILABLE:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><text x="10" y="50" fill="red">RDKit not available</text></svg>', 200, {'Content-Type': 'image/svg+xml'}

    try:
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><text x="10" y="50" fill="red">Invalid SMILES</text></svg>', 200, {'Content-Type': 'image/svg+xml'}

        from rdkit.Chem.Draw import rdMolDraw2D
        drawer = rdMolDraw2D.MolDraw2DSVG(400, 300)
        opts = drawer.drawOptions()
        opts.setBackgroundColour((0.969, 0.984, 0.969, 1.0))
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()

        return svg, 200, {'Content-Type': 'image/svg+xml'}
    except Exception as e:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><text x="10" y="50" fill="red">Error: {e}</text></svg>', 200, {'Content-Type': 'image/svg+xml'}


@app.route('/api/dry/molecule_3d', methods=['GET'])
def api_dry_molecule_3d():
    """Generate 3D SDF for a SMILES string (real-time, no file storage)."""
    smiles = request.args.get('smiles', '').strip()
    if not smiles:
        return jsonify({'ok': False, 'message': 'smiles is required'}), 400

    if not RDKIT_AVAILABLE:
        return jsonify({'ok': False, 'message': 'RDKit not available'}), 500

    try:
        from rdkit.Chem import AllChem
        mol = Chem.MolFromSmiles(smiles)
        if not mol:
            return jsonify({'ok': False, 'message': 'Invalid SMILES'}), 400

        mol = Chem.AddHs(mol)
        res = AllChem.EmbedMolecule(mol, randomSeed=42)
        if res == -1:
            # Retry with random coordinates for complex molecules
            params = AllChem.ETKDGv3()
            params.randomSeed = 42
            params.useRandomCoords = True
            res = AllChem.EmbedMolecule(mol, params)
        if res == -1:
            return jsonify({'ok': False, 'message': 'Cannot generate 3D conformation for this molecule'}), 400

        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
        except Exception:
            pass  # MMFF may fail but coordinates are still valid

        sdf = Chem.MolToMolBlock(mol)
        return sdf, 200, {'Content-Type': 'chemical/x-mdl-sdfile'}
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500


