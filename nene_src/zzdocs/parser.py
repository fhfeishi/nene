# app/zzdocs/parser.py
# document parsing utility  # mineru, docling


import logging
from pathlib import Path 
from typing import Union, Optional, Any, List, Dict
import subprocess
import tempfile
from abc import abstractmethod


class MinerUExecutionError(Exception):
    """catch mineru execution errors"""
    
    def __init__(self, return_code, error_msg):
        self.return_code = return_code
        self.error_msg = error_msg
        super().__init__(
            f"MinerU execution failed with return code {return_code}: {error_msg}"
        )
        
        
class ParserBase:
    """base class for document parsing utility.
    
    """
    # file format supported 
    OFFICE_FORMATS = [".docx", ".doc", ".xls", ".xlsx", ".ppt", ".pptx"]
    TEXT_FORMATS = [".txt", ".md"]
    IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",".tiff", ".tif", ".heic", ".heif"]
    PDF_FORMATS = [".pdf"]
    # + 
    # AUDIO_FORMATS = [".mp3", ".wav", ".ogg", ".m4a", ".aac"]
    # VIDEO_FORMATS = [".mp4", ".avi", ".mkv", ".mov", ".wmv"]
    # CODE_FORMATS = [".py", ".js", ".html", ".css", ".java", ".cpp", ".c", ".h", ".hpp", ".hxx"]
    # OTHER_FORMATS = []
    
    # class level logging 
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    def __init__(self) -> None:
        """initialize the parser"""
        pass 
   
    @classmethod
    def office2pdf(cls, doc_path: Union[Path, str], output_dir:Optional[Path] = None) -> Path:
        """convert office documents to pdf
        requires libreoffice to be installed and in the PATH
        Args:
            doc_path  : path to the office document
            output_dir: directory to save the pdf file
        Returns:
            Path to the generated pdf file
        """
        try:
            # convert to Path object for easier handling
            doc_path = Path(doc_path)
            if not doc_path.exists():
                raise FileNotFoundError(f"office document file not found: {doc_path}")
            if not doc_path.is_file():
                raise IsADirectoryError(f"office document file is a directory: {doc_path}")
            if doc_path.suffix.lower() not in cls.OFFICE_FORMATS:
                raise ValueError(f"Unsupported office document format: {doc_path.suffix}")
            # check if libreoffice is installed and in the PATH
            
            stem = doc_path.stem
            
            # prepare output directory
            if output_dir:
                output_dir_base = Path(output_dir)
            else:
                output_dir_base = doc_path.parent / "libreoffice_output"
            output_dir_base.mkdir(parents=True, exist_ok=True)
            
            # create temporary directory for the conversion
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_pdf_path = Path(temp_dir) 
                
                # convert to pdf using libreoffice
                cls.logger.info(f"Converting {doc_path} to pdf using libreoffice ...")
                
                # prepare subprocess parameters to hide console window on Windows
                import platform
                
                # try  LibreOffice commands in order of preference 
                commands_to_try = ["libreoffice", "soffice", "lowriter"]
                
                conversion_successful = False
                for cmd in commands_to_try:
                    try:
                        # run libreoffice to convert the document to pdf
                        convert_cmd = [
                            cmd, 
                            "--headless", 
                            "--convert-to", 
                            "pdf", 
                            "--outdir", 
                            str(doc_path), 
                            str(temp_dir)]
                        # prepare conversion subprocess parameters
                        convert_subprocess_kwargs = {
                            "capture_output": True,
                            "text"          : True,
                            "timeout"       : 60, # 60 second timeout 
                            "encoding"      : "utf-8",
                            "errors"        : "ignore",
                        }
                        
                        # Hide console window on Windows
                        if platform.system() == "Windows":
                            convert_subprocess_kwargs["creationflags"]=(
                                subprocess.CREATE_NO_WINDOW
                            )
                        
                        result = subprocess.run(
                            convert_cmd, **convert_subprocess_kwargs
                        )
                        
                        if result.returncode == 0:
                            conversion_successful = True 
                            cls.logger.info(f"Successfully converted {doc_path.name} to PDF usding {cmd}")
                            break 
                        else:
                            cls.logger.warning(
                                f"LibreOffice command '{cmd}' failed: {result.stderr}"
                            )
                    except FileNotFoundError:
                        cls.logger.warning(f"LibreOffice command '{cmd}' not found")
                    except subprocess.TimeoutExpired:
                        cls.logger.warning(f"LibreOffice command '{cmd}' timed out")
                    except Exception as e:
                        cls.logger.warning(f"Failed to convert {doc_path} to pdf using {cmd}: {e}")
                if not conversion_successful:
                    raise RuntimeError(
                        f"LibreOffice conversion failed for {doc_path.name}. "
                        f"Please ensure LibreOffice is installed:\n"
                        "- Windows: Download from https://www.libreoffice.org/download/download/\n"
                        "- macOS: brew install --cask libreoffice\n"
                        "- Ubuntu/Debian: sudo apt-get install libreoffice\n"
                        "- CentOS/RHEL: sudo yum install libreoffice\n"
                        "Alternatively, convert the document to PDF manually."
                    )
                    
                
                # find the generated PDF
                pdf_files = list(temp_pdf_path.glob("*.pdf"))
                if not pdf_files:
                    raise RuntimeError(
                        f"PDF conversion failed for {doc_path.name} - no PDF file generated. "
                        f"Please check LibreOffice installation or try manual conversion."
                    )
                
                pdf_path = pdf_files[0]
                cls.logger.info(
                    f"Generated PDF: {pdf_path.name} ({pdf_path.stat().st_size} bytes)"
                )
                
                # validate the generated pdf
                if pdf_path.stat().st_size < 100:  # very small file, like empty
                    raise RuntimeError(
                        "Generated PDF appears to be empty or corrupted. "
                        "Original file may have issues or LibreOffice conversion failed."
                    )
                
                # copy pdf to final output dir
                pdf_path_dst = output_dir_base / f"{stem}.pdf"
                import shutil
                shutil.copy2(pdf_path, pdf_path_dst)
                
                return pdf_path_dst

        except Exception as e:
            cls.logger.error(f"Failed to convert office document to pdf: {e}")
            raise e
    
    @classmethod
    def text2pdf(cls, text_path: Union[Path, str], output_dir:Optional[Path] = None) -> Path:
        """convert text、md files to pdf

        Args:
            text_path (Union[Path, str]): path to the text or md file
            output_dir (Optional[Path], optional): directory to save the pdf file. Defaults to None.

        Returns:
            Path: path to the generated pdf file
        """
        try:
            # convert to Path object for easier handling
            text_path = Path(text_path)
            if not text_path.exists():
                raise FileNotFoundError(f"text or md file not found: {text_path}")
            if not text_path.is_file():
                raise IsADirectoryError(f"text or md file is a directory: {text_path}")
            if text_path.suffix.lower() not in cls.TEXT_FORMATS:
                raise ValueError(f"Unsupported text or md file format: {text_path.suffix}")
            # check if libreoffice is installed and in the PATH
            
            # read the text content
            try:
                with open(text_path, "r", encoding="utf-8") as f:
                    text_content = f.read()
            except UnicodeDecodeError:
                # Try with different encodings
                for encoding in ["gbk", "latin-1", "cp1252"]:
                    try:
                        with open(text_path, "r", encoding=encoding) as f:
                            text_content = f.read()
                        cls.logger.info(
                            f"Successfully read file with {encoding} encoding"
                        )
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    raise RuntimeError(
                        f"Could not decode text file {text_path.name} with any supported encoding"
                    )
                    
            # Prepare output directory
            if output_dir:
                base_output_dir = Path(output_dir)
            else:
                base_output_dir = text_path.parent / "reportlab_output"

            base_output_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = base_output_dir / f"{text_path.stem}.pdf"

            # Convert text to PDF
            cls.logger.info(f"Converting {text_path.name} to PDF...")
            
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import inch
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont

                support_chinese = True
                try:
                    if "WenQuanYi" not in pdfmetrics.getRegisteredFontNames():
                        if not Path(
                            "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc"
                        ).exists():
                            support_chinese = False
                            cls.logger.warning(
                                "WenQuanYi font not found at /usr/share/fonts/wqy-microhei/wqy-microhei.ttc. Chinese characters may not render correctly."
                            )
                        else:
                            pdfmetrics.registerFont(
                                TTFont(
                                    "WenQuanYi",
                                    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
                                )
                            )
                except Exception as e:
                    support_chinese = False
                    cls.logger.warning(
                        f"Failed to register WenQuanYi font: {e}. Chinese characters may not render correctly."
                    )
                    
                # Create PDF document
                doc = SimpleDocTemplate(
                    str(pdf_path),
                    pagesize=A4,
                    leftMargin=inch,
                    rightMargin=inch,
                    topMargin=inch,
                    bottomMargin=inch,
                )    
                    
                # Get styles
                styles = getSampleStyleSheet()
                normal_style = styles["Normal"]
                heading_style = styles["Heading1"]
                if support_chinese:
                    normal_style.fontName = "WenQuanYi"
                    heading_style.fontName = "WenQuanYi"

                # Try to register a font that supports Chinese characters
                try:
                    # Try to use system fonts that support Chinese
                    import platform

                    system = platform.system()
                    if system == "Windows":
                        # Try common Windows fonts
                        for font_name in ["SimSun", "SimHei", "Microsoft YaHei"]:
                            try:
                                from reportlab.pdfbase.cidfonts import (
                                    UnicodeCIDFont,
                                )

                                pdfmetrics.registerFont(UnicodeCIDFont(font_name))
                                normal_style.fontName = font_name
                                heading_style.fontName = font_name
                                break
                            except Exception:
                                continue
                    elif system == "Darwin":  # macOS
                        for font_name in ["STSong-Light", "STHeiti"]:
                            try:
                                from reportlab.pdfbase.cidfonts import (
                                    UnicodeCIDFont,
                                )

                                pdfmetrics.registerFont(UnicodeCIDFont(font_name))
                                normal_style.fontName = font_name
                                heading_style.fontName = font_name
                                break
                            except Exception:
                                continue
                except Exception:
                    pass  # Use default fonts if Chinese font setup fails

                # Build content
                story = []

                # Handle markdown or plain text
                if text_path.suffix.lower() == ".md":
                    # Handle markdown content - simplified implementation
                    lines = text_content.split("\n")
                    for line in lines:
                        line = line.strip()
                        if not line:
                            story.append(Spacer(1, 12))
                            continue

                        # Headers
                        if line.startswith("#"):
                            level = len(line) - len(line.lstrip("#"))
                            header_text = line.lstrip("#").strip()
                            if header_text:
                                header_style = ParagraphStyle(
                                    name=f"Heading{level}",
                                    parent=heading_style,
                                    fontSize=max(16 - level, 10),
                                    spaceAfter=8,
                                    spaceBefore=16 if level <= 2 else 12,
                                )
                                story.append(Paragraph(header_text, header_style))
                        else:
                            # Regular text
                            story.append(Paragraph(line, normal_style))
                            story.append(Spacer(1, 6))
                else:
                    # Handle plain text files (.txt)
                    cls.logger.info(
                        f"Processing plain text file with {len(text_content)} characters..."
                    )

                    # Split text into lines and process each line
                    lines = text_content.split("\n")
                    line_count = 0

                    for line in lines:
                        line = line.rstrip()
                        line_count += 1

                        # Empty lines
                        if not line.strip():
                            story.append(Spacer(1, 6))
                            continue

                        # Regular text lines
                        # Escape special characters for ReportLab
                        safe_line = (
                            line.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        )

                        # Create paragraph
                        story.append(Paragraph(safe_line, normal_style))
                        story.append(Spacer(1, 3))

                    cls.logger.info(f"Added {line_count} lines to PDF")

                    # If no content was added, add a placeholder
                    if not story:
                        story.append(Paragraph("(Empty text file)", normal_style))

                # Build PDF
                doc.build(story)
                cls.logger.info(
                    f"Successfully converted {text_path.name} to PDF ({pdf_path.stat().st_size / 1024:.1f} KB)"
                )    
                    
            except ImportError:
                raise RuntimeError(
                    "reportlab is required for text-to-PDF conversion. "
                    "Please install it using: pip install reportlab"
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to convert text file {text_path.name} to PDF: {str(e)}"
                ) 
                      
        except Exception as e:
            cls.logger.error(f"Failed to convert text or md file to pdf: {e}")
            raise e
            
    
    @classmethod
    def _process_inlineMD(cls, text: str) -> str:
        """
        Process inline markdown formatting (bold, italic, code, links)
        
        Args:
            text: Raw text with markdown formatting

        Returns:
            Text with ReportLab markup
        """
        
        import re

        # Escape special characters for ReportLab
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Bold text: **text** or __text__
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__(.*?)__", r"<b>\1</b>", text)

        # Italic text: *text* or _text_ (but not in the middle of words)
        text = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", r"<i>\1</i>", text)
        text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<i>\1</i>", text)

        # Inline code: `code`
        text = re.sub(
            r"`([^`]+?)`",
            r'<font name="Courier" size="9" color="darkred">\1</font>',
            text,
        )

        # Links: [text](url) - convert to text with URL annotation
        def link_replacer(match):
            link_text = match.group(1)
            url = match.group(2)
            return f'<link href="{url}" color="blue"><u>{link_text}</u></link>'

        text = re.sub(r"\[([^\]]+?)\]\(([^)]+?)\)", link_replacer, text)

        # Strikethrough: ~~text~~
        text = re.sub(r"~~(.*?)~~", r"<strike>\1</strike>", text)

        return text
    
    @abstractmethod
    def parse_pdf(
        self,
        pdf_path: Union[str, Path],
        output_dir: Optional[str] = None,
        method: str = "auto",
        lang: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Abstract method to parse PDF document.
        Must be implemented by subclasses.

        Args:
            pdf_path: Path to the PDF file
            output_dir: Output directory path
            method: Parsing method (auto, txt, ocr)
            lang: Document language for OCR optimization
            **kwargs: Additional parameters for parser-specific command

        Returns:
            List[Dict[str, Any]]: List of content blocks
        """
        ...

    @abstractmethod
    def parse_image(
        self,
        image_path: Union[str, Path],
        output_dir: Union[str]=None,
        lang: Optional[str]=None,
        **kwargs,
    ) -> List[Dict[str,Any]]:
        
        ... 
    
    @abstractmethod
    def parse_document(
        self,
        file_path: Union[str, Path],
        method: str = "auto",
        output_dir: Optional[str] = None,
        lang: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Abstract method to parse a document.
        Must be implemented by subclasses.

        Args:
            file_path: Path to the file to be parsed
            method: Parsing method (auto, txt, ocr)
            output_dir: Output directory path
            lang: Document language for OCR optimization
            **kwargs: Additional parameters for parser-specific command

        Returns:
            List[Dict[str, Any]]: List of content blocks
        """
        ...
    
    @abstractmethod
    def check_installation(self) -> bool:
        """
        Abstract method to check if the parser is properly installed.
        Must be implemented by subclasses.

        Returns:
            bool: True if installation is valid, False otherwise
        """
        ...


class MineruParser(ParserBase):
    """  
    MinerU (> 2.0) document parsing utility class 
    support parse PDF or image files input,
    convert the content into structured data and geenerate markdown and JSON output.
    """
    
    __slots__ = ()
    
    # class level logging 
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    def __init__(self) -> None:
        """initialize the parser"""
        super().__init__()
    
    @classmethod
    def _run_mineru_command(
        cls,
        input_path: Union[str, Path],
        output_dir: Union[str, Path],
        method: str = "auto",
        lang: Optional[str] = None,
        backend: Optional[str] = None,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
        formula: bool = True,
        table: bool = True,
        device: Optional[str] = None,
        source: Optional[str] = None,
        vlm_url: Optional[str] = None,
    ) -> None:
        """run the mineru command line tool
        Args:
            input_path: Path to input file or directory
            output_dir: Output directory path
            method: Parsing method (auto, txt, ocr)
            lang: Document language for OCR optimization
            backend: Parsing backend
            start_page: Starting page number (0-based)
            end_page: Ending page number (0-based)
            formula: Enable formula parsing
            table: Enable table parsing
            device: Inference device
            source: Model source
            vlm_url: When the backend is `vlm-http-client`, you need to specify the server_url
        """
        cmd = [
            "mineru",
            "-p",
            str(input_path),
            "-o",
            str(output_dir),
            "-m",
            method,
        ]
        
        if backend:                   cmd.extend(["-b", backend])
        if source:                    cmd.extend(["--source", source])
        if lang:                      cmd.extend(["-l", lang])
        if start_page is not None:    cmd.extend(["-s", str(start_page)])
        if end_page is not None:      cmd.extend(["-e", str(end_page)])
        if not formula:               cmd.extend(["-f", "false"])
        if not table:                 cmd.extend(["-t", "false"])
        if device:                    cmd.extend(["-d", device])
        if vlm_url:                   cmd.extend(["-u", vlm_url])

        output_lines = []
        error_lines = []
        
        try:
            # prepare subprocess parameters to hide console window on Windows
            import platform 
            import threading 
            from queue import Queue, Empty 
            
            # log the command  being executed 
            cls.logger.info(f"Executeing mineru command:{' '.join(cmd)}")
        
            subprocess_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text":True,
                "encoding": 'utf-8',
                "errors": "ignore",
                "bufsize": 1, # line buffered
            }
        
            # Hide console window on Windows
            if platform.system() == 'Windows':
                subprocess_kwargs["createflags"] = subprocess.CREATE_NO_WINDOW
                
            # Function to read output from subprocess and add to queue
            def enqueue_output(pipe, queue, prefix):
                try:
                    for line in iter(pipe.readline, ""):
                        if line.strip():  # Only add non-empty lines
                            queue.put((prefix, line.strip()))
                    pipe.close()
                except Exception as e:
                    queue.put((prefix, f"Error reading {prefix}: {e}"))

            # Start subprocess
            process = subprocess.Popen(cmd, **subprocess_kwargs)

            # Create queues for stdout and stderr
            stdout_queue = Queue()
            stderr_queue = Queue()

            # Start threads to read output
            stdout_thread = threading.Thread(
                target=enqueue_output, args=(process.stdout, stdout_queue, "STDOUT")
            )
            stderr_thread = threading.Thread(
                target=enqueue_output, args=(process.stderr, stderr_queue, "STDERR")
            )

            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()

            # Process output in real time
            while process.poll() is None:
                # Check stdout queue
                try:
                    while True:
                        prefix, line = stdout_queue.get_nowait()
                        output_lines.append(line)
                        # Log mineru output with INFO level, prefixed with [MinerU]
                        cls.logger.info(f"[MinerU] {line}")
                except Empty:
                    pass

                # Check stderr queue
                try:
                    while True:
                        prefix, line = stderr_queue.get_nowait()
                        # Log mineru errors with WARNING level
                        if "warning" in line.lower():
                            cls.logger.warning(f"[MinerU] {line}")
                        elif "error" in line.lower():
                            cls.logger.error(f"[MinerU] {line}")
                            error_message = line.split("\n")[0]
                            error_lines.append(error_message)
                        else:
                            cls.logger.info(f"[MinerU] {line}")
                except Empty:
                    pass

                # Small delay to prevent busy waiting
                import time

                time.sleep(0.1)

            # Process any remaining output after process completion
            try:
                while True:
                    prefix, line = stdout_queue.get_nowait()
                    output_lines.append(line)
                    cls.logger.info(f"[MinerU] {line}")
            except Empty:
                pass

            try:
                while True:
                    prefix, line = stderr_queue.get_nowait()
                    if "warning" in line.lower():
                        cls.logger.warning(f"[MinerU] {line}")
                    elif "error" in line.lower():
                        cls.logger.error(f"[MinerU] {line}")
                        error_message = line.split("\n")[0]
                        error_lines.append(error_message)
                    else:
                        cls.logger.info(f"[MinerU] {line}")
            except Empty:
                pass

            # Wait for process to complete and get return code
            return_code = process.wait()

            # Wait for threads to finish
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

            if return_code != 0 or error_lines:
                cls.logger.info("[MinerU] Command executed failed")
                raise MinerUExecutionError(return_code, error_lines)
            else:
                cls.logger.info("[MinerU] Command executed successfully")

        except MinerUExecutionError:
            raise
        except subprocess.CalledProcessError as e:
            cls.logger.error(f"Error running mineru subprocess command: {e}")
            cls.logger.error(f"Command: {' '.join(cmd)}")
            cls.logger.error(f"Return code: {e.returncode}")
            raise
        except FileNotFoundError:
            raise RuntimeError(
                "mineru command not found. Please ensure MinerU 2.0 is properly installed:\n"
                "pip install -U 'mineru[core]' or uv pip install -U 'mineru[core]'"
            )
        except Exception as e:
            error_message = f"Unexpected error running mineru command: {e}"
            cls.logger.error(error_message)
            raise RuntimeError(error_message) from e
            
        


class DoclingParser(ParserBase):
    pass 



        
def main():
    pass 



if __name__ == '__main__':
    main()



