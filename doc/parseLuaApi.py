# pip install markdown pygments jsonschema
import json
import markdown
import xml.etree.ElementTree as ET
from pygments import lex
from pygments.lexers import LuaLexer
from pygments.token import Token
from jsonschema import validate, ValidationError

INPUT_FILE = './lua_api.md'
SCHEMA_FILE = './lua_api.schema.json'
OUTPUT_FILE = 'lua_api.json'

def highlight_lua(code_text):
    tokens = []
    try:
        for token_type, value in lex(code_text, LuaLexer()):
            # Skip purely whitespace tokens (Token.Text or Token.Text.Whitespace)
            if token_type in (Token.Text, Token.Text.Whitespace) and not value.strip():
                continue
            
            tokens.append({"token_type": str(token_type), "value": value})
    except Exception:
        # Fallback
        tokens.append({"token_type": "Text", "value": code_text})
    return tokens

def parse_element(elem):
    # Lists
    if elem.tag in ['ul', 'ol']:
        items = [parse_list_item(li) for li in elem]
        return [item for item in items if item]
    
    # Pre/Code Blocks
    if elem.tag == 'pre':
        code_elem = elem.find('code')
        if code_elem is not None:
            text_content = "".join(code_elem.itertext())
            classes = code_elem.get('class', '')
            
            if 'language-lua' in classes:
                return {
                    "type": "code",
                    "language": "lua",
                    "code": highlight_lua(text_content)
                }
            else:
                return {
                    "type": "pre",
                    "content": text_content
                }

    # Standard Text
    text = "".join(elem.itertext()).strip()
    return {"type": "text", "content": text} if text else None

def parse_list_item(li):
    content = []
    
    # 1. Text direct
    if li.text and li.text.strip():
        content.append({"type": "text", "content": li.text.strip()})
    
    # 2. Children
    for child in li:
        processed = parse_element(child)
        if processed:
            content.append(processed)
        
        # 3. Tail text
        if child.tail and child.tail.strip():
            content.append({"type": "text", "content": child.tail.strip()})
            
    # Unwrap if single item
    if len(content) == 1:
        return content[0]
    
    return content

def build_ast(xml_root):
    root_list = []
    stack = [(0, root_list)]

    for child in xml_root:
        # Headers trigger hierarchy
        if child.tag.startswith('h') and len(child.tag) == 2:
            try:
                level = int(child.tag[1])
            except ValueError:
                level = 0
                
            header_text = "".join(child.itertext()).strip()
            
            while stack[-1][0] >= level:
                stack.pop()
            
            new_container = []
            stack[-1][1].append({header_text: new_container})
            stack.append((level, new_container))
        
        # Content
        else:
            node = parse_element(child)
            if node:
                stack[-1][1].append(node)

    return root_list

def main():
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            md_text = f.read()
    except FileNotFoundError:
        print(f"File not found: {INPUT_FILE}")
        return

    # Render to XHTML
    html = markdown.markdown(md_text, extensions=['fenced_code'], output_format='xhtml')
    xml_string = f"<root>{html}</root>"

    try:
        xml_root = ET.fromstring(xml_string)
        ast = build_ast(xml_root)
        
        # Load Schema and Validate
        try:
            with open(SCHEMA_FILE, 'r', encoding='utf-8') as sf:
                schema = json.load(sf)
            validate(instance=ast, schema=schema)
            print("Validation: PASSED")
        except FileNotFoundError:
            print(f"Validation: SKIPPED (Schema file '{SCHEMA_FILE}' not found)")
        except ValidationError as ve:
            print(f"Validation: FAILED - {ve.message}")
        except json.JSONDecodeError:
            print(f"Validation: SKIPPED (Invalid JSON in schema file)")

        # Output to file (compact)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as out_f:
            json.dump(ast, out_f, separators=(',', ':'))
        print(f"Output saved to: {OUTPUT_FILE}")
        
    except ET.ParseError as e:
        debug_filename = "debug_failed_render.xml"
        with open(debug_filename, "w", encoding="utf-8") as f:
            f.write(xml_string)
            
        print(f"\nFATAL XML ERROR: {e}")
        print(f"Full generated XML saved to: {debug_filename}")

        if hasattr(e, 'position'):
            line_num, col = e.position
            lines = xml_string.splitlines()
            idx = line_num - 1
            start = max(0, idx - 5)
            end = min(len(lines), idx + 5)

            print("\n--- CONTEXT OF ERROR ---")
            for i in range(start, end):
                prefix = ">> " if i == idx else "   "
                safe_line = lines[i].encode('ascii', 'replace').decode('ascii')
                print(f"{prefix}Line {i+1}: {safe_line}")
            print("------------------------\n")

if __name__ == "__main__":
    main()
