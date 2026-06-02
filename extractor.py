import os
import re
import fitz  # PyMuPDF

def parse_figure_number(text):
    """
    キャプションの文字列から図番号を数値のタプルとして抽出する。
    例: "図1-2: サンプル" -> (1, 2)
        "Fig 3.4" -> (3, 4)
        "写真5" -> (5, 0)
    """
    # プレフィックス (図, Fig, Figure, 画像, 写真, Photo) にマッチ
    match = re.search(r'(?:図|Fig(?:ure)?\.?|画像|写真|Photo)\s*(\d+)(?:[-.](\d+))?', text, re.IGNORECASE)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else 0
        return (major, minor)
    return None

def get_sorted_images_on_page(page, image_list):
    """
    ページ上の画像をキャプション情報および物理座標に基づいてソートして返す。
    各要素は (img, fig_num_str) のタプルで構成される。
    """
    blocks = page.get_text("blocks")
    captions = []
    
    # 1. キャプションと思われるテキストブロックを抽出
    for b in blocks:
        x0, y0, x1, y1, text, _, _ = b
        text_stripped = text.strip()
        fig_num = parse_figure_number(text_stripped)
        if fig_num:
            captions.append({
                "rect": fitz.Rect(x0, y0, x1, y1),
                "text": text_stripped,
                "fig_num": fig_num
            })
            
    mapped_images = []
    
    # 2. 各画像に対して最適なキャプションを近接度で紐付ける
    for img in image_list:
        xref = img[0]
        rects = page.get_image_rects(xref)
        
        best_caption = None
        
        if rects:
            img_rect = rects[0]
            min_distance = float('inf')
            
            for cap in captions:
                cap_rect = cap["rect"]
                y_gap = cap_rect.y0 - img_rect.y1  # 画像の下端とキャプションの上端の距離
                x_overlap = max(0, min(img_rect.x1, cap_rect.x1) - max(img_rect.x0, cap_rect.x0))
                
                # 画像の直下にあり、距離が近い（例: 80ポイント以内）、かつ水平方向に重なりがある場合
                if 0 <= y_gap < 80 and x_overlap > 0:
                    if y_gap < min_distance:
                        min_distance = y_gap
                        best_caption = cap
                
                # 画像の直上にある場合
                elif -80 < y_gap <= 0 and x_overlap > 0:
                    y_gap_abs = abs(cap_rect.y1 - img_rect.y0)
                    if y_gap_abs < min_distance:
                        min_distance = y_gap_abs
                        best_caption = cap
            has_rect = True
        else:
            img_rect = fitz.Rect(0, 0, 0, 0)
            has_rect = False
            
        mapped_images.append({
            "img": img,
            "rect": img_rect,
            "has_rect": has_rect,
            "fig_num": best_caption["fig_num"] if best_caption else None,
        })
        
    # 3. ソート処理
    with_fig = [m for m in mapped_images if m["fig_num"] is not None]
    without_fig = [m for m in mapped_images if m["fig_num"] is None]
    
    # 図番号でソート
    with_fig.sort(key=lambda x: x["fig_num"])
    # 図番号なしは物理位置（Y座標 -> X座標）でソート
    # 座標が取得できないものは (float('inf'), float('inf')) で末尾寄せにする
    without_fig.sort(key=lambda x: (x["rect"].y0, x["rect"].x0) if x["has_rect"] else (float('inf'), float('inf')))
    
    sorted_mapped = with_fig + without_fig
    
    # 返却値の生成: 各要素について、(img, fig_num_str) のタプルにする
    result = []
    for m in sorted_mapped:
        fig_num_str = None
        if m["fig_num"]:
            major, minor = m["fig_num"]
            fig_num_str = f"{major}-{minor}" if minor > 0 else f"{major}"
        result.append((m["img"], fig_num_str))
        
    return result

def extract_images_from_pdf(pdf_path, output_dir):
    """
    指定されたPDFファイルから画像を抽出し、指定フォルダに保存します。
    
    Args:
        pdf_path (str): 対象のPDFファイルのパス
        output_dir (str): 画像の保存先ディレクトリ
        
    Returns:
        int: 抽出された画像数
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDFファイルが見つかりません: {pdf_path}")
        
    raw_pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    # Windowsのファイル/フォルダ名禁止文字 `<>:"/\|?*` を `_` に置換
    safe_pdf_name = re.sub(r'[<>:"/\\|?*]', '_', raw_pdf_name)
    
    # フォルダ名はサニタイズ後のPDF名にする（末尾のスペースやピリオドは除去）
    folder_name = safe_pdf_name.strip(". ")
    target_output_dir = os.path.join(output_dir, folder_name)
    os.makedirs(target_output_dir, exist_ok=True)
    
    # 絶対パスとしての出力フォルダ名を取得
    abs_target_dir = os.path.abspath(target_output_dir)
    
    # 画像ファイルパス全体の文字数を200文字以下に抑えるため、ファイル名のプレフィックス（PDF名部分）の最大長を計算
    # 算出式: len(abs_target_dir) + 1 (区切り) + len(pdf_name) + len("_page999_fig99-99_99.jpeg") <= 200
    # 安全バッファとして、ページ・図番号サフィックス等の長さを 35 文字とする
    max_pdf_name_len = 200 - len(abs_target_dir) - 1 - 35
    
    if max_pdf_name_len < 5:
        # 極端に短い、またはマイナスの場合はプレフィックスを空にする
        pdf_name = ""
    elif len(safe_pdf_name) > max_pdf_name_len:
        pdf_name = safe_pdf_name[:max_pdf_name_len].strip(". ")
    else:
        pdf_name = safe_pdf_name
    
    # PDFファイルを開く
    doc = fitz.open(pdf_path)
    extracted_count = 0
    
    try:
        # 全ページを走査
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            if not image_list:
                continue
                
            # ハイブリッドソートの実行
            sorted_mapped_images = get_sorted_images_on_page(page, image_list)
            
            # ページ内で使用したサフィックスのカウントを保持する辞書
            suffix_counts = {}
            
            # ページ内の画像を走査
            for img_idx, (img, fig_num_str) in enumerate(sorted_mapped_images):
                xref = img[0]
                smask = img[1]  # 透過マスク(Soft Mask)の xref
                
                # 元画像の基本情報を取得
                base_image = doc.extract_image(xref)
                image_ext = base_image["ext"]
                
                # 命名規則: 図番号がある場合は _fig[図番号]、なければ _[画像連番]
                base_suffix = f"fig{fig_num_str}" if fig_num_str else f"{img_idx + 1}"
                if base_suffix not in suffix_counts:
                    suffix_counts[base_suffix] = 0
                    filename_suffix = base_suffix
                else:
                    suffix_counts[base_suffix] += 1
                    filename_suffix = f"{base_suffix}_{suffix_counts[base_suffix]}"
                
                # 透過マスクが存在する、またはPNG形式である場合、透過を復元する
                if smask > 0 or image_ext.lower() == "png":
                    try:
                        # 元画像のPixmapを作成
                        pix = fitz.Pixmap(doc, xref)
                        
                        # 透過マスクがある場合は結合してアルファチャンネルを作成
                        if smask > 0:
                            mask = fitz.Pixmap(doc, smask)
                            pix = fitz.Pixmap(pix, mask)
                            image_ext = "png"  # 透過保持のためPNGとして保存
                        
                        # カラースペースの調整（RGB/RGBAでない場合は変換）
                        if pix.colorspace.n not in (3, 4):
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                            
                        if pdf_name:
                            filename = f"{pdf_name}_page{page_num + 1}_{filename_suffix}.{image_ext}"
                        else:
                            filename = f"page{page_num + 1}_{filename_suffix}.{image_ext}"
                        filepath = os.path.join(target_output_dir, filename)
                        
                        # PixmapをPNG画像として保存
                        pix.save(filepath)
                        extracted_count += 1
                        continue  # 保存に成功したため、後続のバイナリ保存処理をスキップ
                    except Exception:
                        # Pixmapによる抽出が失敗した場合は、通常のバイナリ抽出へフォールバック
                        pass
                
                # 通常の画像保存処理（透過マスクなし、またはPixmapエラー時）
                image_bytes = base_image["image"]
                if pdf_name:
                    filename = f"{pdf_name}_page{page_num + 1}_{filename_suffix}.{image_ext}"
                else:
                    filename = f"page{page_num + 1}_{filename_suffix}.{image_ext}"
                filepath = os.path.join(target_output_dir, filename)
                
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
                
                extracted_count += 1
    finally:
        doc.close()
        
    return extracted_count


def extract_images_from_folder(input_dir, output_dir, log_callback=None):
    """
    指定されたフォルダ内のすべてのPDFファイルから画像を抽出します。
    
    Args:
        input_dir (str): PDFファイルが格納されたディレクトリ
        output_dir (str): 画像の保存先ディレクトリ
        log_callback (function, optional): ログメッセージを受け取るコールバック関数
        
    Returns:
        tuple (int, int): (処理されたPDFファイル数, 抽出された総画像数)
    """
    if not os.path.exists(input_dir):
        raise FileNotFoundError(f"入力フォルダが見つかりません: {input_dir}")
        
    os.makedirs(output_dir, exist_ok=True)
    
    # PDFファイルのリストを取得（大文字小文字を区別しない）
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    if not pdf_files:
        if log_callback:
            log_callback("入力フォルダ内にPDFファイルが見つかりませんでした。")
        return 0, 0
        
    total_extracted = 0
    processed_files = 0
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(input_dir, pdf_file)
        if log_callback:
            log_callback(f"処理中: {pdf_file} ...")
        try:
            count = extract_images_from_pdf(pdf_path, output_dir)
            total_extracted += count
            processed_files += 1
            if log_callback:
                log_callback(f"  -> 完了: {pdf_file} (抽出画像数: {count}枚)")
        except Exception as e:
            if log_callback:
                log_callback(f"  -> エラー: {pdf_file} の処理中にエラーが発生しました: {str(e)}")
                
    return processed_files, total_extracted
