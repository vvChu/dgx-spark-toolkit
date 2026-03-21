import re

def parse_metadata(filename):
    meta = {'date': 'unknown', 'type': 'unknown', 'authority': 'unknown', 'doc_number': ''}
    date_match = re.search(r'(\d{8})', filename)
    if date_match:
        d = date_match.group(1)
        meta['date'] = f'{d[:4]}-{d[4:6]}-{d[6:]}'
    doc_match = re.search(r'([A-Z]{2,4})(\d+)[-/]([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)', filename)
    if doc_match:
        meta['type'] = doc_match.group(1)
        number = doc_match.group(2)
        authority_part = doc_match.group(3)
        auth_parts = authority_part.split('-')
        non_year = [p for p in auth_parts if not re.match(r'^\d{4}$', p)]
        if non_year:
            meta['authority'] = non_year[-1]
        year_parts = [p for p in auth_parts if re.match(r'^\d{4}$', p)]
        year = year_parts[0] if year_parts else (meta['date'][:4] if meta['date'] != 'unknown' else '')
        type_vn = meta['type']
        auth = meta['authority']
        if year and year != 'unknown':
            meta['doc_number'] = f'{number}/{year}/{type_vn}-{auth}'
        else:
            meta['doc_number'] = f'{number}/{type_vn}-{auth}'
    return meta

test_filenames = [
    'TT01-2023-BTP_Quy_dinh_che_do.pdf',
    'TT12-2018-BTP_Huong_dan.pdf',
    '20250610_QD1111-TTg_Title.pdf',
    '20240824_CV656-TTg-KSTT_MR.pdf',
]

print("=== DOC_ID GENERATION TRACE ===\n")
for fn in test_filenames:
    meta = parse_metadata(fn)
    raw = meta.get('doc_number', '').strip()
    namespace = 'Linh_vuc_BTP'
    is_legal = bool(re.match(r'^\d+/', raw))
    if is_legal:
        doc_id = f'{namespace}/{raw}'
    else:
        clean_fn = fn.replace(' ', '_').replace('.pdf', '')
        if raw:
            doc_id = f'{namespace}/{raw}_{clean_fn}'
        else:
            doc_id = f'{namespace}/{clean_fn}'
    doc_id_safe = re.sub(r'[^\w\d\-_/.]', '_', doc_id)
    
    print(f'File:       {fn}')
    print(f'  doc_num:    {raw!r}')
    print(f'  is_legal:   {is_legal}')
    print(f'  doc_id:     {doc_id}')
    print(f'  sanitized:  {doc_id_safe}')
    print()
