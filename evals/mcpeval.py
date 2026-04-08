"""Example script demonstrating command line arguments in standard Python."""


from collections.abc import Sequence
from absl import app
from absl import flags
import json
import os
import sys
import subprocess
import tempfile
from typing import List, Dict, Any, Tuple
from pathlib import Path
import pydash


# Import local parser instead of google3
import extract_tool_call


# Define flags
_GOLDEN_PROMPT_RESPONSES = flags.DEFINE_string(name="golden_prompts_responses", default=None, help="Path to a Golden Prompts-Responses JSONL file.")
_CLI_PATH = flags.DEFINE_string(name="gemini_cli_path", default="gemini", help="Path to the Gemini CLI binary.")
_LOCAL_MCP_JSON  = flags.DEFINE_multi_string(name="localmcpjson", default=[], help="JSON Config for local MCP server")
_REMOTE_MCP_JSON = flags.DEFINE_multi_string(name="remotemcpjson", default=[], help="JSON Config for remote MCP server")
_PROMPT_PREPEND  = flags.DEFINE_string(name="prompt_prepend", default="", help="Prepend each prompt with this string")
_MAIN_CONTEXT    = flags.DEFINE_string(name="context", default="", help="Context string that will be written to GEMINI.md")
_GOOGLE_ACCOUNT = flags.DEFINE_bool(name="google_account", default=False, help="Use Google Account for authentication instead of Gemini API key.")


def run_ls(directory):
   try:
       result = subprocess.run(['/bin/ls', '-latr', directory],
                               capture_output=True, text=True, check=True)
   except subprocess.CalledProcessError as e:
       pass


def load_jsonl_data(file_path: str) -> tuple[List[Dict[str, Any]], bool]:
   data = []
   original_wd = get_working_directory()
   if original_wd and not os.path.isabs(file_path):
       file_path = os.path.join(original_wd, file_path)


   if not check_file_exists(file_path):
       print(f"JSON File does not exist: {file_path}")
       return data, False


   if not can_read_file(file_path):
       print(f"Error - DO NOT Have permission to read JSON file: {file_path}")
       return data, False


   with open(file_path, "r") as f:
       try:
           data = json.load(f)
           return data, True
       except json.JSONDecodeError as e:
           raise ValueError(f"Failed to parse JSON syntax in {file_path}: {e}")


   return data, True


def can_write_file(filepath):
   try:
       with open(filepath, 'a') as f:
           pass
       return True
   except (OSError, IOError):
       return False


def can_read_file(filepath):
   try:
       with open(filepath, 'r') as f:
           pass
       return True
   except (OSError, IOError):
       return False


def check_file_exists(filepath) -> bool:
   file_path = Path(filepath)
   if file_path.is_file():
       return True
   else:   
       return False


def write_context_to_file(file_path: str) -> None:
   if _MAIN_CONTEXT.value:
       if can_write_file(file_path):
           with open(file_path, "w") as f:
               f.write(_MAIN_CONTEXT.value)


def create_dot_gemini_dir_write_settings_file() -> bool:
   original_wd = get_working_directory()
   if not original_wd:
       return False


   relative_new_dirs = ".gemini"
   full_path = os.path.join(original_wd, relative_new_dirs)


   try:
       os.makedirs(full_path, exist_ok=True)
       test_file_path = os.path.join(full_path, "settings.json")
      
       with open(test_file_path, 'w') as f:
           f.write("{ \n"
                   "  \"mcpServers\": { \n")
           mcp_servers_entries = []
           for json_text in _LOCAL_MCP_JSON.value:
               mcp_servers_entries.append(json_text)
           for json_text in _REMOTE_MCP_JSON.value:
               mcp_servers_entries.append(json_text)
           f.write(",\n".join(mcp_servers_entries))
           f.write("\n   } \n")
           f.write("} \n")


   except OSError as e:
       print(f"Error creating directory structure {full_path}: {e}", file=sys.stderr)
       return False


   return True


def create_local_files_and_dirs_needed() -> bool:
   gemini_md = os.path.join(get_working_directory(), "GEMINI.md")
   write_context_to_file(gemini_md)


   if not create_dot_gemini_dir_write_settings_file():
       print("Could not create .gemini dir")
       return False
   return True


def get_working_directory() -> str:
   return str(os.getcwd())


def is_in_docker() -> bool:
   return os.path.exists('/.dockerenv')


def compare_test_results(full_testrun_data: Dict[str, Any], expected_subset_data: Dict[str, Any]) -> bool:
   return pydash.is_match(full_testrun_data, expected_subset_data)


def run_one_testcase(one_testcase: Any, index: int) -> Dict[str, Any]:
   """
   Executes a single test case and returns a dictionary containing the score
   and the pass/fail status of each individual evaluation metric.
   """
   prompt = one_testcase["prompt"]
   # We print a simple progress indicator so you know it's not frozen
   print(f"[{index}] Evaluating: {prompt[:60]}...")
  
   temp_dir = tempfile.mkdtemp()
   log_file_stdout = os.path.join(temp_dir, "gemini_cli.log.stdout")
   log_file_stderr = log_file_stdout.replace("stdout", "stderr")


   gemini_cli_path = _CLI_PATH.value
   command = f'{gemini_cli_path} --debug -p "{prompt}" 1> {log_file_stdout} 2> {log_file_stderr}'


   # Initialize the result dictionary for this specific prompt
   result_report = {
       "prompt": prompt,
       "score": 0.0,
       "match_result_display": False,
       "match_status": False,
       "match_name": False,
       "match_args": False,
       "error_msg": None
   }


   try:
       subprocess.run(command, shell=True, check=False, capture_output=True, text=True, cwd=get_working_directory())


       if not check_file_exists(log_file_stderr):
           result_report["error_msg"] = "Log file not generated."
           return result_report


       if one_testcase.get("response", {}).get("name"):
           parsed_results_dict = extract_tool_call.parse_log(log_file_stderr)
           if parsed_results_dict:
              
               # Compare ResultDisplay (0.5 pts)
               if compare_test_results(parsed_results_dict.get("resultDisplay"), one_testcase["response"].get("resultDisplay")):
                   result_report["score"] += 0.5
                   result_report["match_result_display"] = True
              
               # Compare Status (0.2 pts)
               if parsed_results_dict.get("status") == "success":
                   result_report["score"] += 0.2
                   result_report["match_status"] = True
              
               # Compare Name (0.15 pts)
               if parsed_results_dict.get("name") == one_testcase["response"].get("name"):
                   result_report["score"] += 0.15
                   result_report["match_name"] = True
                      
               # Compare Arguments (0.15 pts)
               if parsed_results_dict.get("args") == one_testcase["response"].get("args"):
                   result_report["score"] += 0.15
                   result_report["match_args"] = True
              
               # Return the populated report dictionary
               return result_report
           else:
               result_report["error_msg"] = "No tool call found in log file."
               try:
                   with open(log_file_stderr, "r") as f:
                       content = f.read()
                       if "RESOURCE_EXHAUSTED" in content or "429" in content:
                           result_report["error_msg"] = "API Quota Exhausted (429 Error)."
               except Exception:
                   pass
               return result_report
       else:
           result_report["error_msg"] = "Invalid golden JSON format (missing response.name)."
           return result_report
          
   except Exception as e:
       result_report["error_msg"] = f"CRITICAL Exception: {e}"
       return result_report


def print_diagnostic_report(results: List[Dict[str, Any]]):
   """Prints a structured summary of all test cases and their component scores."""
   print("\n" + "="*80)
   print("                 DETAILED EVALUATION REPORT")
   print("="*80)
  
   total_score = 0.0
   perfect_runs = 0
  
   for i, r in enumerate(results, 1):
       total_score += r['score']
      
       # If the score is 1.0, we just note it's perfect to save space
       if r['score'] == 1.0:
           perfect_runs += 1
           continue
          
       # For imperfect scores, we break down exactly what failed
       print(f"\n [Test {i}] FAILED ({r['score']:.2f} / 1.0)")
       print(f"   Prompt: {r['prompt']}")
      
       if r['error_msg']:
           print(f"   Error: {r['error_msg']}")
       else:
           # Print only the components that failed
           if not r['match_name']:
               print("   - FAILED: Tool Name Mismatch")
           if not r['match_args']:
               print("   - FAILED: Arguments Mismatch")
           if not r['match_status']:
               print("   - FAILED: Tool Status was not 'success'")
           if not r['match_result_display']:
               print("   - FAILED: ResultDisplay Mismatch (Golden JSON vs API Output)")


   print("\n" + "="*80)
   print(f"Total Testcases : {len(results)}")
   print(f"Perfect Runs    : {perfect_runs} / {len(results)}")
   print(f"Total Score     : {total_score:.2f} / {len(results):.2f}")
  
   if len(results) > 0:
       print(f"Final Percentage: {(total_score / len(results)) * 100:.2f}%")
   else:
       print("No test cases evaluated.")
   print("="*80 + "\n")


def main(argv: Sequence[str]) -> None:
   if len(argv) != 1:
       print("Usage: python mcpeval.py <json file>")
       sys.exit(1)


   if is_in_docker():
       os.chdir('/tmp')


   if not can_write_file("./GEMINI.md"):
       print("Cannot write to current directory. Exiting!")
       return


   if _GOLDEN_PROMPT_RESPONSES.value is None:
       raise app.UsageError('--golden_prompts_responses=<json file> is required')
  
   if not _LOCAL_MCP_JSON.value and not _REMOTE_MCP_JSON.value:
       raise app.UsageError('At least one of --remotemcpjson or --localmcpjson is required')


   if not create_local_files_and_dirs_needed():
       print("Could not create .gemini directory and/or creating GEMINI.md file")
       return


   json_golden_data, success_reading_json = load_jsonl_data(_GOLDEN_PROMPT_RESPONSES.value)


   if not success_reading_json:
       print("Failure reading JSON")
       return
  
   print("\nStarting Evaluation Pipeline...")
  
   # Store all individual test case results
   all_results = []
  
   for index, one_test_case in enumerate(json_golden_data, 1):
       test_result = run_one_testcase(one_test_case, index)
       all_results.append(test_result)
  
   # Print the final detailed report
   print_diagnostic_report(all_results)


if __name__ == '__main__':
   app.run(main)
