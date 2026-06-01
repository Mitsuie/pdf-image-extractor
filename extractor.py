import os
import fitz  # PyMuPDF

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
        
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    target_output_dir = os.path.join(output_dir, pdf_name)
    os.makedirs(target_output_dir, exist_ok=True)
    
    # PDFファイルを開く
    doc = fitz.open(pdf_path)
    extracted_count = 0
    
    try:
        # 全ページを走査
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            
            # ページ内の画像を走査
            for img_idx, img in enumerate(image_list):
                xref = img[0]
                smask = img[1]  # 透過マスク(Soft Mask)の xref
                
                # 元画像の基本情報を取得
                base_image = doc.extract_image(xref)
                image_ext = base_image["ext"]
                
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
                            
                        # 命名規則: [PDF名]_page[ページ番号]_[画像連番].[拡張子]
                        filename = f"{pdf_name}_page{page_num + 1}_{img_idx + 1}.{image_ext}"
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
                filename = f"{pdf_name}_page{page_num + 1}_{img_idx + 1}.{image_ext}"
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
