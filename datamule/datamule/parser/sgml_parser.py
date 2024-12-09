import os
import json
from io import BytesIO, StringIO
import uu
from typing import Dict, Optional, TextIO

class CPythonSGMLParser:
    """
    Optimized SGML parser for CPython that processes SGML submissions with improved memory usage
    and better performance characteristics.
    """
    def __init__(self, buffer_size: int = 1024 * 1024):
        self.buffer_size = buffer_size
        self._tag_cache: Dict[str, str] = {}  # Cache for frequently seen tags

    def _extract_tag_content(self, line: str) -> Optional[tuple[str, str]]:
        """Extract tag and content using cached operations and string methods."""
        try:
            if not (line.startswith('<') and '>' in line):
                return None
                
            # Use cached tag lookup for better performance
            tag_end = line.index('>')
            tag = line[1:tag_end]
            
            if tag.startswith('/'):
                return None
                
            # Cache the tag for future lookups
            if tag not in self._tag_cache:
                self._tag_cache[tag] = tag
            
            content = line[tag_end + 1:].strip()
            return (self._tag_cache[tag], content)
        except (ValueError, IndexError):
            return None

    def _write_document_content(self, text_buffer: list, current_document: dict, output_dir: str) -> None:
        """Write document content to file, handling both text and uuencoded content."""
        if not text_buffer:
            return

        content = ''.join(text_buffer)
        
        # Determine output filename
        if 'FILENAME' in current_document:
            output_path = os.path.join(output_dir, current_document['FILENAME'])
        else:
            output_path = os.path.join(output_dir, f"{current_document.get('SEQUENCE', 'unknown')}.txt")
        
        # Process content based on encoding
        first_line = content.partition('\n')[0].strip()
        if first_line.startswith('begin '):
            # Handle uuencoded content
            with BytesIO(content.encode()) as input_file:
                uu.decode(input_file, output_path, quiet=True)
        else:
            # Handle plain text content
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)

    def parse_file(self, filepath: str, output_dir: str) -> None:
        """
        Parse SGML file with optimized CPython operations.
        
        Args:
            filepath: Path to input SGML file
            output_dir: Directory to store output files
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Use StringIO for building metadata JSON
        metadata_buffer = StringIO()
        metadata_buffer.write('{"submission": {}, "documents": [\n')
        
        submission_data: Dict[str, str] = {}
        current_document: Dict[str, str] = {}
        text_buffer: list[str] = []
        
        state = {
            'in_document': False,
            'in_text': False,
            'in_submission': True,
            'first_document': True
        }
        
        # Process file with larger buffer for better I/O performance
        with open(filepath, 'r', buffering=self.buffer_size, encoding='utf-8') as file:
            for line in file:
                stripped = line.strip()
                
                # Handle state changes
                if stripped == '<DOCUMENT>':
                    state['in_document'] = True
                    state['in_submission'] = False
                    if not state['first_document']:
                        metadata_buffer.write(',\n')
                    current_document = {}
                    
                elif stripped == '</DOCUMENT>':
                    # Write document metadata
                    metadata_buffer.write(json.dumps(current_document))
                    state['first_document'] = False
                    
                    # Process document content
                    self._write_document_content(text_buffer, current_document, output_dir)
                    text_buffer = []
                    state['in_document'] = False
                    current_document = {}
                    
                elif stripped == '<TEXT>':
                    state['in_text'] = True
                    text_buffer = []
                    
                elif stripped == '</TEXT>':
                    state['in_text'] = False
                    
                elif state['in_text']:
                    if stripped not in ['<PDF>', '</PDF>']:
                        text_buffer.append(line)
                        
                else:
                    # Process tags
                    tag_content = self._extract_tag_content(stripped)
                    if tag_content:
                        key, value = tag_content
                        if state['in_submission']:
                            submission_data[key] = value
                        elif state['in_document']:
                            current_document[key] = value
        
        # Finalize metadata
        metadata_buffer.write('\n]}')
        metadata_str = metadata_buffer.getvalue()
        metadata_buffer.close()
        
        # Write final metadata file
        metadata_path = os.path.join(output_dir, 'metadata.json')
        metadata = json.loads(metadata_str)
        metadata['submission'] = submission_data
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4)

def parse_sgml_submission(filepath: str, output_dir: Optional[str] = None, header_only: bool = False) -> None:
    """
    Parse an SGML submission file.
    
    Args:
        filepath: Path to the SGML file to parse
        output_dir: Directory to store output files (created if doesn't exist)
        header_only: If True, only parse headers (not implemented)
    """
    if header_only:
        raise NotImplementedError("Header-only parsing not implemented")
    
    if output_dir is None:
        output_dir = os.path.splitext(filepath)[0] + '_output'
        
    parser = CPythonSGMLParser()
    parser.parse_file(filepath, output_dir)