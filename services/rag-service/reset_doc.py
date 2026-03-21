import sys; sys.path.insert(0, '/app')
from ingestion.state_manager import PostgresStateManager

sm = PostgresStateManager()  # reads from env

rel_path = 'VB phap quy/Linh vuc_BXD-GTVT/Quy chuan BGTVT ban hanh/QCVN 113-2023-BGTVT_Ve phuongphapthuvanhbanhmoto-ganmay.pdf'

# Check current status
status = sm.get_status(rel_path)
print(f'Current status: {status}')

# Reset to PENDING to force re-process
sm.update_status(rel_path, 'PENDING', error=None)
print(f'Reset to PENDING: {rel_path}')
print('rag-watcher will pick it up on next scan.')
