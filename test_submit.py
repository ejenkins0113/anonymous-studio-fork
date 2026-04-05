import sys
sys.path.insert(0, r'\\wsl.localhost\Ubuntu\home\51nk0r5w1m\school\capstone\v2_anonymous-studio')
import taipy.gui.gui_actions as ga
ga.get_state_id = lambda state: "123"


import app
import time

class MockState:
    job_file_content = 'test.csv'
    job_file_name = 'test.csv'
    job_entities = app.ALL_ENTITIES[:]
    job_operator = 'replace'
    job_threshold = 0.35
    job_chunk_size = 500
    job_spacy_model = 'auto'
    job_compute_backend = 'auto'
    job_dask_min_rows = 250000
    job_mongo_write_batch = 500
    job_card_id = ''
    active_job_id = ''
    job_is_running = False
    job_progress_pct = 0
    job_progress_msg = ''
    job_progress_status = ''
    job_expected_rows = 0
    job_active_started = 0
    job_view_tab = 'Results'
    job_quality_md = ''

state = MockState()
sid = app.get_state_id(state)
app._FILE_CACHE[sid] = {'bytes': b'header\nsome pii data\n', 'name': 'test.csv'}

print('Submitting job...')
try:
    app.on_submit_job(state)
    print('Submitted. Status:', state.job_progress_msg)
except Exception as e:
    import traceback
    traceback.print_exc()

print('Done test.')
