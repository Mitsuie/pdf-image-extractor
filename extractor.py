from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
from typing import Callable
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# パス長制限の最大文字数（Windows MAX_PATH 260 を見越した制限値）
MAX_PATH_LENGTH = 200
# パス長計算時にページ番号・サフィックス・拡張子のために確保する安全バッファ文字数
PATH_BUFFER_LENGTH = 35
# プレフィックス（PDF名部分）として採用する最小文字数（これ未満ならプレフィックスを空にする）
MIN_PREFIX_LENGTH = 5
# 画像とキャプションの近接判定に用いる最大距離（ポイント）
CAPTION_DISTANCE_THRESHOLD = 80.0
# ファイル名・フォルダ名に使用できない禁止文字の正規表現
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')
# 図番号・キャプション抽出用の正規表現
FIGURE_NUMBER_PATTERN = re.compile(
    r'(?:図|Fig(?:ure)?\.?|画像|写真|Photo)\s*(\d+)(?:[-.](\d+))?',
    re.IGNORECASE,
)

# 図番号を表す型エイリアス（メジャー番号, マイナー番号）
FigureNumber = tuple[int, int]


@dataclass(frozen=True)
class Caption:
    """ページ内のキャプション候補情報を保持するデータクラス。"""
    rect: fitz.Rect
    text: str
    fig_num: FigureNumber


@dataclass
class PageImage:
    """ページ内の画像および紐付けられたキャプション情報を保持するデータクラス。"""
    img: tuple
    rect: fitz.Rect
    has_rect: bool
    fig_num: FigureNumber | None


def parse_figure_number(text: str) -> FigureNumber | None:
    """
    キャプションの文字列から図番号を数値のタプルとして抽出する。
    例: "図1-2: サンプル" -> (1, 2)
        "Fig 3.4" -> (3, 4)
        "写真5" -> (5, 0)

    Args:
        text (str): キャプションと思われるテキスト

    Returns:
        FigureNumber | None: (メジャー番号, マイナー番号) のタプル。マッチしない場合は None
    """
    match = FIGURE_NUMBER_PATTERN.search(text)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else 0
        return (major, minor)
    return None


def format_figure_number(fig_num: FigureNumber | None) -> str | None:
    """
    図番号タプルを表示用・ファイル名用の文字列に整形する。

    Args:
        fig_num (FigureNumber | None): (メジャー番号, マイナー番号) のタプル、または None

    Returns:
        str | None: 整形後の文字列（例: "1-2", "3"）。fig_num が None の場合は None
    """
    if fig_num is None:
        return None
    major, minor = fig_num
    return f"{major}-{minor}" if minor > 0 else f"{major}"


def sanitize_filename(name: str) -> str:
    """
    ファイル名やフォルダ名に使用できない禁止文字をアンダースコアに置換する。

    Args:
        name (str): サニタイズ対象の文字列

    Returns:
        str: サニタイズ後の文字列
    """
    return INVALID_FILENAME_CHARS.sub('_', name)


def build_folder_name(safe_name: str) -> str:
    """
    サニタイズされた名前から末尾・先頭の空白やピリオドを除去してフォルダ名を生成する。

    Args:
        safe_name (str): サニタイズ済みの文字列

    Returns:
        str: フォルダ名
    """
    return safe_name.strip(". ")


def compute_file_prefix(safe_name: str, abs_target_dir: str) -> str:
    """
    パス長制限（MAX_PATH_LENGTH）を考慮してファイル名のプレフィックス（PDF名部分）を決定する。

    Args:
        safe_name (str): サニタイズ済みのPDFファイル名
        abs_target_dir (str): 保存先ディレクトリの絶対パス

    Returns:
        str: 決定されたファイル名プレフィックス
    """
    max_pdf_name_len = MAX_PATH_LENGTH - len(abs_target_dir) - 1 - PATH_BUFFER_LENGTH
    if max_pdf_name_len < MIN_PREFIX_LENGTH:
        return ""
    elif len(safe_name) > max_pdf_name_len:
        return safe_name[:max_pdf_name_len].strip(". ")
    else:
        return safe_name


def resolve_suffix(base_suffix: str, suffix_counts: dict[str, int]) -> str:
    """
    同名サフィックスの衝突を防ぐため、2回目以降の出現に連番を付与する。

    Args:
        base_suffix (str): ベースとなるサフィックス（例: "fig1-1", "1"）
        suffix_counts (dict[str, int]): 各サフィックスの出現回数を記録する辞書

    Returns:
        str: 解決された一意のサフィックス（例: "fig1-1", "fig1-1_1"）
    """
    if base_suffix not in suffix_counts:
        suffix_counts[base_suffix] = 0
        return base_suffix
    else:
        suffix_counts[base_suffix] += 1
        return f"{base_suffix}_{suffix_counts[base_suffix]}"


def generate_image_filename(prefix: str, page_number: int, suffix: str, ext: str) -> str:
    """
    抽出画像の保存ファイル名を生成する。

    Args:
        prefix (str): ファイル名接頭辞（PDF名由来、空文字可）
        page_number (int): 1から始まるページ番号
        suffix (str): 画像のサフィックス（図番号または連番）
        ext (str): ファイルの拡張子（例: "jpeg", "png"）

    Returns:
        str: 組み立てられたファイル名
    """
    if prefix:
        return f"{prefix}_page{page_number}_{suffix}.{ext}"
    return f"page{page_number}_{suffix}.{ext}"


def _build_pixmap(doc: fitz.Document, xref: int, smask: int) -> fitz.Pixmap:
    """
    画像の Pixmap を作成し、必要に応じて透過マスクの結合およびカラースペースの変換を行う。

    Args:
        doc (fitz.Document): PDF ドキュメントオブジェクト
        xref (int): 元画像の xref 番号
        smask (int): 透過マスクの xref 番号（0 の場合はマスクなし）

    Returns:
        fitz.Pixmap: 生成・調整された Pixmap オブジェクト
    """
    pix = fitz.Pixmap(doc, xref)
    if smask > 0:
        mask = fitz.Pixmap(doc, smask)
        pix = fitz.Pixmap(pix, mask)
    if pix.colorspace and pix.colorspace.n not in (3, 4):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return pix


def _save_image(
    doc: fitz.Document,
    img: tuple,
    base_image: dict,
    page_number: int,
    suffix: str,
    prefix: str,
    target_dir: str,
) -> None:
    """
    画像を 1 枚保存する。透過マスクや PNG の場合は Pixmap 経由で保存し、
    失敗した場合は元のバイナリデータのまま保存する（フォールバック）。

    Args:
        doc (fitz.Document): PDF ドキュメントオブジェクト
        img (tuple): get_images() の要素タプル (xref, smask, ...)
        base_image (dict): extract_image(xref) の戻り値辞書
        page_number (int): 1から始まるページ番号
        suffix (str): 画像のサフィックス（図番号または連番）
        prefix (str): ファイル名接頭辞
        target_dir (str): 保存先ディレクトリパス
    """
    xref = img[0]
    smask = img[1]
    orig_ext = base_image["ext"]
    saved = False

    if smask > 0 or orig_ext.lower() == "png":
        try:
            pix = _build_pixmap(doc, xref, smask)
            ext = "png" if smask > 0 else orig_ext
            filename = generate_image_filename(prefix, page_number, suffix, ext)
            filepath = os.path.join(target_dir, filename)
            pix.save(filepath)
            saved = True
        except Exception as e:
            logger.warning(
                "Pixmapでの保存に失敗したため、元データのまま保存します (page=%d, xref=%d): %s",
                page_number,
                xref,
                e,
            )

    if not saved:
        filename = generate_image_filename(prefix, page_number, suffix, orig_ext)
        filepath = os.path.join(target_dir, filename)
        with open(filepath, "wb") as f:
            f.write(base_image["image"])


def get_sorted_images_on_page(page: fitz.Page, image_list: list[tuple]) -> list[tuple[tuple, str | None]]:
    """
    ページ上の画像をキャプション情報および物理座標に基づいてソートして返す。
    各要素は (img, fig_num_str) のタプルで構成される。

    Args:
        page (fitz.Page): 対象ページのオブジェクト
        image_list (list[tuple]): page.get_images() で取得された画像情報タプルのリスト

    Returns:
        list[tuple[tuple, str | None]]: (img_tuple, fig_num_str) のソート済みリスト
    """
    blocks = page.get_text("blocks")
    captions: list[Caption] = []

    # 1. キャプションと思われるテキストブロックを抽出
    for b in blocks:
        x0, y0, x1, y1, text, _, _ = b
        text_stripped = text.strip()
        fig_num = parse_figure_number(text_stripped)
        if fig_num:
            captions.append(Caption(
                rect=fitz.Rect(x0, y0, x1, y1),
                text=text_stripped,
                fig_num=fig_num,
            ))

    mapped_images: list[PageImage] = []

    # 2. 各画像に対して最適なキャプションを近接度で紐付ける
    for img in image_list:
        xref = img[0]
        rects = page.get_image_rects(xref)

        best_caption: Caption | None = None

        if rects:
            img_rect = rects[0]
            min_distance = float('inf')

            for cap in captions:
                cap_rect = cap.rect
                y_gap = cap_rect.y0 - img_rect.y1  # 画像の下端とキャプションの上端の距離
                x_overlap = max(0, min(img_rect.x1, cap_rect.x1) - max(img_rect.x0, cap_rect.x0))

                # 画像の直下にあり、距離が近い（閾値以内）、かつ水平方向に重なりがある場合
                if 0 <= y_gap < CAPTION_DISTANCE_THRESHOLD and x_overlap > 0:
                    if y_gap < min_distance:
                        min_distance = y_gap
                        best_caption = cap

                # 画像の直上にある場合
                elif -CAPTION_DISTANCE_THRESHOLD < y_gap <= 0 and x_overlap > 0:
                    y_gap_abs = abs(cap_rect.y1 - img_rect.y0)
                    if y_gap_abs < min_distance:
                        min_distance = y_gap_abs
                        best_caption = cap
            has_rect = True
        else:
            img_rect = fitz.Rect(0, 0, 0, 0)
            has_rect = False

        mapped_images.append(PageImage(
            img=img,
            rect=img_rect,
            has_rect=has_rect,
            fig_num=best_caption.fig_num if best_caption else None,
        ))

    # 3. ソート処理
    with_fig = [m for m in mapped_images if m.fig_num is not None]
    without_fig = [m for m in mapped_images if m.fig_num is None]

    # 図番号でソート
    with_fig.sort(key=lambda x: x.fig_num)
    # 図番号なしは物理位置（Y座標 -> X座標）でソート
    # 座標が取得できないものは (float('inf'), float('inf')) で末尾寄せにする
    without_fig.sort(key=lambda x: (x.rect.y0, x.rect.x0) if x.has_rect else (float('inf'), float('inf')))

    sorted_mapped = with_fig + without_fig

    # 返却値の生成: 各要素について、(img, fig_num_str) のタプルにする
    result: list[tuple[tuple, str | None]] = []
    for m in sorted_mapped:
        result.append((m.img, format_figure_number(m.fig_num)))

    return result


def extract_images_from_pdf(pdf_path: str, output_dir: str) -> int:
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

    # Windowsのファイル/フォルダ名禁止文字を置換
    safe_pdf_name = sanitize_filename(raw_pdf_name)

    # フォルダ名はサニタイズ後のPDF名にする（末尾のスペースやピリオドは除去）
    folder_name = build_folder_name(safe_pdf_name)
    target_output_dir = os.path.join(output_dir, folder_name)
    os.makedirs(target_output_dir, exist_ok=True)

    # 絶対パスとしての出力フォルダ名を取得
    abs_target_dir = os.path.abspath(target_output_dir)

    # パス長制限を考慮してファイル名プレフィックスを決定
    pdf_name = compute_file_prefix(safe_pdf_name, abs_target_dir)

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
            suffix_counts: dict[str, int] = {}

            # ページ内の画像を走査
            for img_idx, (img, fig_num_str) in enumerate(sorted_mapped_images):
                xref = img[0]

                # 元画像の基本情報を取得
                base_image = doc.extract_image(xref)

                # 命名規則: 図番号がある場合は _fig[図番号]、なければ _[画像連番]
                base_suffix = f"fig{fig_num_str}" if fig_num_str else f"{img_idx + 1}"
                filename_suffix = resolve_suffix(base_suffix, suffix_counts)

                # 画像を保存
                _save_image(
                    doc=doc,
                    img=img,
                    base_image=base_image,
                    page_number=page_num + 1,
                    suffix=filename_suffix,
                    prefix=pdf_name,
                    target_dir=target_output_dir,
                )
                extracted_count += 1
    finally:
        doc.close()

    return extracted_count


def extract_images_from_folder(
    input_dir: str,
    output_dir: str,
    log_callback: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    """
    指定されたフォルダ内のすべてのPDFファイルから画像を抽出します。

    Args:
        input_dir (str): PDFファイルが格納されたディレクトリ
        output_dir (str): 画像の保存先ディレクトリ
        log_callback (Callable[[str], None] | None, optional): ログメッセージを受け取るコールバック関数

    Returns:
        tuple[int, int]: (処理されたPDFファイル数, 抽出された総画像数)
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
