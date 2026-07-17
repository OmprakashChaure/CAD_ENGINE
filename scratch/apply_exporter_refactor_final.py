from pathlib import Path

target_file = Path("pipeline/dataset_pipeline.py")
content = target_file.read_text(encoding="utf-8")

replacement_block_file = Path("scratch/replacement_block.txt")
replacement_code = replacement_block_file.read_text(encoding="utf-8")

# Define the start and end anchors for the replacement block
start_anchor = "    def _build_tasks_from_semantic("
end_anchor = "                new_obj[k] = self._mask_context_leakage(v, target_val, target_prop, original_property)\n            return new_obj\n        elif isinstance(obj, list):\n            return [self._mask_context_leakage(x, target_val, target_prop, original_property) for x in obj]\n        else:\n            return obj"

# Locate the block to replace
start_idx = content.find(start_anchor)
if start_idx == -1:
    print("Error: Start anchor not found!")
    exit(1)

end_idx = content.find(end_anchor, start_idx)
if end_idx == -1:
    # Try with raw CRLF just in case
    end_anchor_crlf = "                new_obj[k] = self._mask_context_leakage(v, target_val, target_prop, original_property)\r\n            return new_obj\r\n        elif isinstance(obj, list):\r\n            return [self._mask_context_leakage(x, target_val, target_prop, original_property) for x in obj]\r\n        else:\r\n            return obj"
    end_idx = content.find(end_anchor_crlf, start_idx)
    if end_idx == -1:
        print("Error: End anchor not found!")
        exit(1)
    else:
        end_idx += len(end_anchor_crlf)
else:
    end_idx += len(end_anchor)

# Insert the replacement block
content_new = content[:start_idx] + replacement_code + content[end_idx:]
target_file.write_text(content_new, encoding="utf-8")
print("Successfully refactored dataset_pipeline.py for high quality engineering semantics!")
