import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def generate_excel_data(users, target_username="data", scrape_type="followers"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data Instagram"

    # Title Banner
    ws.merge_cells("A1:K1")
    title_cell = ws["A1"]
    title_cell.value = f"Instagram Scraper Report - @{target_username} ({scrape_type.capitalize()})"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # Headers
    headers = [
        "No",
        "Username",
        "Nama Lengkap",
        "Kategori / Status",
        "Followers",
        "Following",
        "Email Publik",
        "Status Akun",
        "Centang Biru",
        "Sumber Target",
        "Link Profil"
    ]

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )

    ws.append([]) # Row 2 empty
    ws.row_dimensions[2].height = 8

    ws.append(headers) # Row 3
    ws.row_dimensions[3].height = 24

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=3, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    # Data Rows
    row_idx = 4
    for idx, u in enumerate(users, 1):
        username = str(u.get("username", ""))
        full_name = str(u.get("full_name", ""))
        category = str(u.get("category_type") or "Follower Biasa")
        f_cnt = str(u.get("follower_count_str") or u.get("followers_count") or u.get("follower_count") or "-")
        g_cnt = str(u.get("following_count_str") or u.get("following_count") or "-")
        email = str(u.get("email") or "-")
        status_akun = "Privat" if u.get("is_private") else "Publik"
        verified = "Ya" if u.get("is_verified") else "Tidak"
        sumber = str(u.get("target_source") or target_username)
        link = f"https://www.instagram.com/{username}/"

        row = [
            idx,
            f"@{username}",
            full_name,
            category,
            f_cnt,
            g_cnt,
            email,
            status_akun,
            verified,
            f"@{sumber}",
            link
        ]
        ws.append(row)
        ws.row_dimensions[row_idx].height = 20

        # Styling
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border
            if col_idx in [1, 5, 6, 8, 9]:
                cell.alignment = center_align
            else:
                cell.alignment = left_align

            # Highlight email cell
            if col_idx == 7 and email != "-":
                cell.fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
                cell.font = Font(name="Calibri", size=10, bold=True, color="166534")

            # Zebra striping
            elif row_idx % 2 == 1:
                cell.fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        row_idx += 1

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row > 2 and cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
