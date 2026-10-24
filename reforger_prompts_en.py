"""English texts for the model and the user (from 2.0.0): the same constant names and the same {fields}
as reforger_prompts.py. Used when the language is set to "en" (REFORGER_LANG=en or "lang": "en" in
assistant_web_data/settings.json); reforger_prompts.py then replaces its Polish constants with these.
tests: every constant here must exist in reforger_prompts.py with identical {fields}."""


SYSTEM_PROMPT = """
You are a technical assistant specializing in Arma Reforger modding
and Enfusion / Enforce Script.

Always communicate with the user in English.
Keep original API names, class names and code identifiers unchanged.

CORE PRINCIPLES
- Treat Enfusion MCP BK as the primary source of truth for game-specific code.
- Do not invent classes, methods, parameters, events or file paths.
- Distinguish verified facts from assumptions.
- An API declaration, successful compilation and correct runtime behavior
  are three different levels of verification.
- Do not claim that code works unless it has actually been tested.

TOOLS (exact names; no other tools exist)
- api_search(query, limit): classes, methods, enums of the script API.
- asset_search(query, type, limit): searches file NAMES only, not file content.
  Use type 'script' for class names (SCR_*, *Component, *UserAction); type 'prefab' only for prefab names.
- game_read(path): reads one game file (script, prefab, config).
- game_browse(path, pattern): lists a directory; pattern is ONLY an extension filter ("*.c", "*.et").
- component_search, wiki_search, wiki_read, wb_knowledge.
There is NO search, grep, browser, python or shell tool. Never call them.
Paths: scripts/Game/generated/<Group>/X.c are API stubs (proto external);
scripts/Game/... and scripts/GameCode/... are game code; Prefabs/... are prefabs.
If game_read fails, take the real path from the asset_search hint or run asset_search.
api_search and asset_search return SIMILAR names when the exact one does not exist. Read the
first line of each result: "[Exact match ...]" means found; "[NO EXACT MATCH
...]" means the name was NOT found. Then never describe that name as existing and never use it
in code or in a "verified" list.
api_search covers class members only. Global functions (Print, PrintFormat, ...) and general
Enforce Script questions: use wiki_search and then wiki_read the best page (search returns only
truncated snippets). wiki_read takes the page TITLE exactly as in the "## Title" header of a wiki_search
result (e.g. "Scripting: Conventions"), never the Source URL or its Arma_Reforger:... slug.
game_read also accepts query (search text inside the WHOLE file) and line_start/line_end.
When a file is shown shortened, use query instead of guessing what the omitted part contains.
game_browse "pattern" filters by file EXTENSION only ("*.c"); to find files by part of the name use asset_search.
For a method or field name use api_search with type=method. If a name is not found after 2-3
differently spelled searches, say that it was not found; do not keep guessing further names.
Every API name used in code must be confirmed by a tool result in this conversation. When the user
reports a compile error or says code does not work, verify each name with api_search before answering
and never repeat a name the compiler rejected (also not in another form, e.g. GetGame().X).
Enforce Script has no ternary operator ?: , no ?. operator and no float suffix (write 0.5, not 0.5f).
In overrides call super.Method(...) unless you intentionally replace the behaviour; a modded class
changes ALL instances of that class. Before writing code for an unfamiliar system, call wb_knowledge with
the topic (e.g. "replication", "entity lifecycle", "enforce language pitfall").
Terminology: muzzle = the barrel / muzzle of a weapon (NOT the magazine); magazine = magazine.
Check inherited methods on the declared base type (e.g. IEntity), not only on the
concrete class, and read the parent class when a method is not listed.
For questions about how something is configured in a prefab, find and read a real vanilla
prefab that uses that component (asset_search with the prefab name, then game_read).
Never describe prefab fields you have not read.

CODE RESEARCH
- Use asset_search to discover files and game_read to inspect their contents.
- Use api_search to investigate classes and methods.
- Before generating code, inspect the relevant base classes,
  method signatures and existing implementation patterns.
- If a tool fails, do not treat the attempted lookup as evidence.
- Prefer a few relevant source files over reading many unrelated files.
- For questions about Enforce Script syntax, modding mechanisms,
  and engine concepts, consult wiki_search and wiki_read before
  relying on general programming knowledge.

ENFORCE SCRIPT
- Enforce Script is not C++ or C#. Do not assume identical syntax
  or engine lifecycle behavior.
- Understand the difference between ordinary inheritance and modded classes.
- "class Child : Parent" creates a new derived class.
- "modded class ExistingClass" modifies an existing class through
  Enforce Script's modding mechanism.
- Verify lifecycle callbacks, member accessibility and method signatures
  before using them in generated code.
- Never assume a class or component can be attached to a prefab
  without checking how that mechanism works.
- When modifying the behavior of an existing game script class,
  prefer "modded class ExistingClass" where appropriate.
- Do not use ordinary inheritance as a substitute for modifying
  an existing class. Use inheritance when a genuinely new class is needed.
- Changing prefab configuration or component attributes is not
  the same as modifying an existing script class.

USER INTENT
- Respect the context of the ongoing conversation.
- Do not silently reinterpret units, values or requirements.
- If an ambiguity fundamentally changes the implementation,
  ask one brief clarifying question.

OUTPUT
- Describe methods using only the comments from files you actually read;
  if there is no comment, say so. Do not invent examples of usage.
- Never invent literal values (icon names, localization keys, GUIDs, field names).
  Copy them from files you read, or mark them "INVENTED - replace".
- Label code "from game code" ONLY if it is copied verbatim from a game_read result you received;
  anything you write yourself is a "sketch" (e.g. "This code is a sketch"). Never attribute code to a file you did not read.
- Never write "seen in the API" or "verified" for a name unless it appears in a tool result.
- Quote line numbers only if they come from a local game_read view (they match the file); never guess them.
- Components are obtained with FindComponent(Type) and Type.Cast(...) as in game code;
  there is no GetComponent<T>().
- Provide practical, focused answers without unnecessary explanations.
- Explain what was verified and what still requires testing.
- Do not modify files or operate Workbench.
- Generate code only as a proposal for the user to review!
""".strip()


EMERGENCY_PLACEHOLDER = ("[Emergency answer: synthesis without full research. Its content was not verified and is not "
                         "a source of facts; the user saw it in the chat window. Check game facts in the tools again.]")


WIKI_TITLE_HINT = ("\n[Hint: in wiki_read give the title exactly as in the '## Title' header of the wiki_search result "
                   "(e.g. 'Scripting: Conventions'), without the address, without the 'Arma Reforger:' prefix and without "
                   "underscores. The 'Did you mean' suggestion is often wrong.]")


# ---------------------------------------------------------------- hints during a turn
HINT_EMPTY_NO_TOOLS = (
    "[System note] The previous answer was empty. First call the MCP tools "
    "(api_search, asset_search, game_read) to verify the facts in the game, "
    "then answer in text.")

HINT_RETRY_AFTER_EMPTY = (
    "[System note] The previous generation ended without answer text (reasoning too "
    "long). Write the final answer to the user's question NOW, in the requested format, "
    "based only on the tool results above. Do not call tools and do not reason at length.")

HINT_INCOMPLETE_RETRY = (
    "The previous answer was cut off in the middle. Give the whole "
    "answer again, this time concise and complete. No tables. "
    "Base conclusions only on the MCP results from this conversation. "
    "If you do not have enough data, say so directly.")

HINT_API_FIX = (                      # {problems}
    "[System note] Your answer uses names in code that no tool result in this "
    "conversation confirms: {problems}. Before you answer, check them "
    "with api_search (type=method or class). If a name is not in the results, do not use it "
    "and find the correct one. Then write the full answer again.")

HINT_STALL = (                        # {ledger}
    "[System note] The last calls gave no new data (you are repeating the same ones). "
    "{ledger}"
    " Do not repeat them and do not guess further names. If you are missing a file, find its path "
    "with asset_search (file name; type=script for classes, type=prefab for prefabs). "
    "For a method or field name use api_search with type=method. If the name is not found after 2-3 "
    "different spellings, say it was not found. If you already have enough data, write the answer.")

HINT_COMPILE_ERROR = (                # {symbols} {lookup}
    "[System note] The compiler reported that these do not exist: {symbols}"
    ". Do not use these names again (also not in another form, e.g. GetGame().X instead of "
    "ArmaReforgerScripted.X). {lookup}"
    "Use only methods confirmed in the tool results; search further if needed.")
HINT_COMPILE_ERROR_LOOKUP = "Results of the automatic check:\n\n{results}\n\n"   # {results}

# ---------------------------------------------------------------- tool answers made up by the engine
TOOL_DUP_IN_CONTEXT = (               # {ledger}
    "You already have this result in context (earlier in the conversation) - do not repeat this call. "
    "{ledger} Take a NEW step or write the answer.")
TOOL_DUP_BLOCKED = (                  # {ledger}
    "ERROR: an identical call was already made in this turn. {ledger}"
    " Choose a different step (e.g. asset_search by file name) or summarize the results.")
TOOL_VIEW_LIMIT = (                   # {limit} {ledger}
    "ERROR: limit of {limit} local views of this file in one turn. {ledger}"
    " Change strategy or write the answer from what you have.")
TOOL_MCP_LIMIT = "ERROR: the MCP call limit was reached. Answer only based on the results received so far."
TOOL_FILE_SHORTENED = (               # {chars}
    "\n[The file has {chars} characters; the context holds a shortened version. Use game_read with "
    "the query parameter (search in the WHOLE file) or line_start/line_end, "
    "instead of guessing what is in the omitted part.]")

# ---------------------------------------------------------------- messages for the user
MSG_EMPTY_TWICE = (
    "The model returned an empty answer twice and made no MCP reads "
    "in this turn. I am not guessing the answer. Try again or ask a shorter question.")
NOTE_INCOMPLETE = (
    "[Note: Ollama returned an incomplete answer. "
    "Try making the question more specific or increasing the available context.]")

# ---------------------------------------------------------------- emergency synthesis (no tools)
SYNTH_NO_EVIDENCE = (                 # {cause}
    "No confirmed MCP results could be collected in this turn ({cause}). "
    "I am not giving an answer from the model's memory, because it would be unverified. "
    "Try again or ask a shorter question. The call history is in the MCP panel.")
SYNTH_INSTRUCTIONS = (                # {question} {evidence}
    "You have no access to any tools now. This is the final stage of the answer. "
    "Answer the user's question in English based on the results below. "
    "Do not describe unverified examples as working code. "
    "List as missing ONLY what really is not in the results below; "
    "search them carefully first. "
    "Do not suggest new tool calls; do not write out function calls. "
    "The answer must be useful and concise.\n\n"
    "USER QUESTION: {question}\n\nMCP READ RESULTS:\n{evidence}")
SYNTH_SYSTEM_SUFFIX = "\nNow answer without tools. Do not generate tool_calls."
SYNTH_SECOND_ATTEMPT = (
    "Write plain text in English only. Do not use tools. "
    "Summarize the confirmed facts and the gaps; no code that was not verified.\n\n")
SYNTH_FOOTER = "\n\n_[Summary of the available MCP results: {cause}; the answer may be incomplete.]_"   # {cause}
SYNTH_FAILED = (                      # {cause}
    "The answer could not be prepared ({cause}). "
    "The model did not return complete text even in a separate synthesis "
    "without tools. The collected MCP results are visible in the panel; "
    "no ready solution was confirmed.")

# ---------------------------------------------------------------- check footers (chat window only)
FOOTER_VERIFY = "\n\n_[Automatic quote verification: {shown}{more}]_"     # {shown} {more}
FOOTER_VERIFY_MORE = "; (+{n} more)"                                       # {n}
FOOTER_API = "\n\n_[API check: not confirmed in tool results: {problems}. Check these names before use.]_"  # {problems}


# ---------------------------------------------------------------- compiler errors with a line, syntax, read tools
HINT_COMPILE_LINES = (                # {errors} {kb} {project}
    "[System note] The compiler reported errors:\n\n{errors}\n\n{kb}{project}"
    "Fix exactly the indicated statement and give the whole corrected code; do not guess other causes.")
COMPILE_LINE_FOUND = (                # {file} {line} {message} {excerpt} {findings}
    "{file}, line {line}: {message}\nIf the file contains the code from your last answer, "
    "this line is (>> marks the indicated line):\n{excerpt}{findings}")
COMPILE_LINE_FINDINGS = "\nDetected in this line: {findings}."           # {findings}
COMPILE_LINE_MISSING = (              # {file} {line} {message}
    "{file}, line {line}: {message}\nI did not find this line in your last code (the file may have been changed).")
COMPILE_KB = "Enforce Script syntax pitfalls (BK knowledge base, wb_knowledge):\n{sections}\n\n"   # {sections}
COMPILE_PROJECT = "You can read the current content of the file with project (action='read').\n"
HINT_SYNTAX_FIX = (                   # {problems}
    "[System note] Your code contains syntax that Enforce Script does not accept: {problems}. "
    "Fix these places and write the full answer again.")
FOOTER_SYNTAX = "\n\n_[Syntax check: {problems}. Fix before compiling.]_"     # {problems}
TOOL_ACTION_BLOCKED = "action {action!r} of tool {tool} is not available (read-only: {allowed})"  # {action} {tool} {allowed}
TOOL_READ_ONLY_NOTE = " [This assistant is read-only: allowed actions: {allowed}.]"               # {allowed}


# ---------------------------------------------------------------- knowledge before code
HINT_KB_CHECK = (                         # {query} {files} {excerpt} {question}
    "[System note] Before you send the code, compare it with the patterns from the BK knowledge base "
    "(wb_knowledge('{query}'), files: {files}):\n\n{excerpt}\n\n"
    "If the patterns show a different, correct way (e.g. which class to modify, where to put the server check, "
    "when to call super, how many times an overridden method runs), fix the code. If your code agrees with them, "
    "leave it. The patterns serve ONLY to check your code: do not describe them, do not judge whether they match "
    "the documentation and do not add code the user did not ask for. Then write the full answer again "
    "to the user's question:\n«{question}»")


# ----------------------------------------------------------------
EMERGENCY_CODE_HEADER = ("\n\nCode from this answer (UNCHECKED - the user may have copied and compiled it; "
                         "it is the reference point for reported errors):\n\n")
API_QUERY_REWRITTEN = "query {old!r} -> {new!r} (api_search searches by name)"                         # {old} {new}
API_CLASS_SEEN = "method {method} is in the results also for class {cls}"                              # {method} {cls}
API_CLASS_NOT_SEEN = ("method {method} exists (in: {owners}); for class {cls} it is not visible in the shown "
                      "results - the list may be cut, check api_search(query='{cls}', type='class')")    # {method} {owners} {cls}


# ----------------------------------------------------------------
NOTE_GLOBAL_FUNCTION = (              # {name} {info}
    "[Global function '{name}()': api_search indexes only class members, so global functions are not in it. "
    "This does NOT mean that '{name}' does not exist. {info}]")
NOTE_GLOBAL_OWNERS = ("\n[Class methods with the same name (this is NOT the global function; do not create objects of "
                      "these classes to use it): {owners}]")                                         # {owners}
NOTE_PARENTS = (                      # {name} {path} {chain} {bk} {members} {first}
    "\n[Assistant addition: the api_search data has a wrong hierarchy for {name} ({bk}); the 'Inherits from', "
    "'Direct subclasses' lines and inherited methods above may be incomplete or misleading. Real hierarchy (source: {path}): "
    "{chain}. Methods of the base classes (names only):\n{members}\n"
    "Full signatures: api_search(query='{first}', type='class', limit=1).]")
API_GAME_INSTANCE = "{cls}.{meth}: this is a method of the game object - call it via GetGame().{meth}(...)"   # {cls} {meth}
API_CHAIN_NOT_SEEN = "{shown}: not in the tool results for {cls} and its base classes ({chain})"            # {shown} {cls} {chain}


# ----------------------------------------------------------------
TOOL_BROWSE_PATTERN = (               # {pattern} {frag}
    "pattern {pattern!r} will not work: in game_browse the pattern is ONLY an extension filter ('*.c', '*.et'), "
    "any other pattern returns only directories. Find files by part of the name with asset_search(query='{frag}'), "
    "a method or field name with api_search(query='{frag}', type='method'). The call did not use up the limit.")
TOOL_ASSET_CODE_QUERY = (             # {query}
    "asset_search searches only file NAMES, and {query!r} looks like a code fragment. Check a method name with "
    "api_search(type='method'), a global function (Print, GetGame) with wiki_search, a file by class name with "
    "asset_search(query='ClassName', type='script'). The call did not use up the limit.")
API_EXACT_CLASS_NOTE = "'{name}' is an exact class name -> full class view (type=class, limit=1)"   # {name}
HINT_FINAL_NO_TOOLS = (               # {cause}
    "[System note] The search has ended ({cause}); tools are no longer available. Write the final "
    "answer to the user's question NOW based on the tool results above. Describe what you did not find "
    "directly as not found; do not guess names. Do not call tools.")
FOOTER_STOPPED = ("\n\n_[Search stopped ({cause}); answer based on the collected results, "
                  "may be incomplete.]_")                                                             # {cause}
API_DECL_NO_CLASS = "{decl}: class {target} is not in the tool results (API)"                          # {decl} {target}
API_DECL_NO_OVERRIDE = "override {meth} in {cls}: no method {meth} in {target} and its base classes"     # {meth} {cls} {target}


# ----------------------------------------------------------------
TOOL_CONTENT_SEARCH = (               # {name}
    "There is no tool {name!r} and no search in the content of many files. Find a method or field with "
    "api_search(query='Name', type='method'), a file by name with asset_search(query='Name', type='script'), "
    "and text in a known file with game_read(path='...', query='text'). The call did not use up the limit.")
HINT_QUOTE_FIX = (                    # {problems}
    "[System note] Quotes in your answer do not match the files that were read: {problems}. "
    "Copy code labelled as from the game VERBATIM from the game_read result, or say next to it that it is a sketch. "
    "Give line numbers only from a file view (game_read with line_start/line_end or query); otherwise remove them.")
QUOTE_LINES_NOT_SEEN = ("line numbers {refs} do not come from any file view in this conversation "
                        "(game_read does not number lines; marked ⚠ in the text)")                     # {refs}


# ----------------------------------------------------------------
API_DECL_NO_IMPLICIT = "{meth}() in {cls}: no method {meth} in {target} and its base classes (call without an object)"  # {meth} {cls} {target}
QUESTION_FILES_NOTE = ("\n\n[Engine: game files with names mentioned in the question (exact file name from asset_search): "
                       "{files}. Start with them (game_read).]")                                      # {files}


# ----------------------------------------------------------------
API_SCR_TAG_CLASS = ("class {cls}: the SCR_ prefix is the prefix of game classes (Bohemia), and this is a new mod class - "
                     "use your own mod tag (e.g. TAG_{rest})")                                       # {cls} {rest}
API_SCR_TAG_TEXT = ("the answer recommends the SCR_ prefix for mod classes, but SCR_ is the game's prefix (Bohemia); "
                    "a mod uses its own unique tag (e.g. TAG_)")
API_RETURN_TYPE = ("{decl}: {meth}() returns {ret} (tool results), but the result is assigned to type {typ}")  # {decl} {meth} {ret} {typ}
SYNTAX_PREFAB_JSON = ("prefab entry (.et) written as JSON - .et files are not JSON; entry format: "
                      "Class \"{GUID}\" { Field value }, as in the Weapon_Base.et that was read")
MARK_QUOTE_BLOCK = ("> ⚠ **Engine note:** this fragment was not found in the file `{path}` - it is NOT a verbatim "
                    "quote from the game.\n\n")                                                       # {path}
MARK_SYNTAX_BLOCK = "> ⚠ **Engine note:** {problem}\n\n"                                             # {problem}
MARK_LINE_REF = " ⚠"


# ----------------------------------------------------------------
DOC_HIERARCHY_SOURCE = "Workbench API documentation (hierarchy.html)"
NOTE_SUBCLASSES = ("\n[Assistant addition: the 'Direct subclasses' list above is wrong for {name}. "
                   "Direct subclasses according to the Workbench API documentation: {subs}.]")      # {name} {subs}
NOTE_SEARCH_MISS_FILE = ("\n[Engine: api_search does not know '{name}', but the game files contain a file with exactly this name: {files}. "
                         "Read it (game_read) before you write that {name} does not exist.]")        # {name} {files}
SYNTAX_PRINTFORMAT = ("PrintFormat uses the placeholders %1..%9 (e.g. PrintFormat(\"x: %1\", x)), not %s/%d: "
                      "`{line}`")                                                                     # {line}
SYNTAX_ENTRY_CLASS = ("the prefab entry uses class {entry}, but the new class in the script is {cls} - "
                      "the class name in the .et entry must be the same as in the script")           # {entry} {cls}
MARK_UNREAD_BLOCK = ("> ⚠ **Engine note:** the assistant did not read the file `{path}` in this conversation - this fragment is NOT "
                     "a confirmed quote from the game.\n\n")                                          # {path}
MARK_API_BLOCK = "> ⚠ **Engine note:** {problem}\n\n"                                                # {problem}
NOTE_GLOBAL_DECL = ("\n[Engine: declaration of the global function '{name}' from the game file {path} (verbatim fragment, "
                    "you may quote it with the file name):\n```c\n{decl}\n```]")                       # {name} {path} {decl}


# ----------------------------------------------------------------
HINT_COMPILE_FULL_CODE = (
    "[System note] The user reported a compile error in their script, and your answer contains no corrected code. "
    "Give the WHOLE corrected script in one code block (not just a fragment and not only a description), with the "
    "indicated line fixed. Use only names confirmed in the tool results.")
API_ENUM_NOT_SEEN = ("{enum}.{value}: the value {value} is not in the tool results (the declaration of {enum} was not read) - "
                     "check it before use")                                                           # {enum} {value}
HINT_BUDGET = (                       # {used} {limit} {ledger}
    "[System note] {used} of {limit} tool calls in this turn are used. {ledger} "
    "Check only the names still missing for the answer (first read the file of the class the question is about, "
    "if you have not read it yet). When you have enough data, write the answer; describe what you did not find directly.")
NOTE_ENUM_DECL = ("\n[Engine: declaration of '{name}' from the game file {path} (verbatim excerpt; only these values exist):\n"
                  "```c\n{decl}\n```]")                                                              # {name} {path} {decl}


if __name__ == "__main__":
    # Kontrola tłumaczenia: python reforger_prompts_en.py  (te same nazwy stałych i te same pola {nazwa} co w PL).
    import os
    import string
    import sys
    os.environ["REFORGER_LANG"] = "pl"
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import reforger_prompts as _pl

    def _fields(text: str):
        try:
            return sorted({f[1] for f in string.Formatter().parse(text) if f[1] is not None})
        except ValueError:          # tekst bez .format() z nawiasami klamrowymi (np. SYNTAX_PREFAB_JSON)
            return None

    pl_names = {k for k in vars(_pl) if k.isupper() and not k.startswith("_")}
    en_names = {k for k in globals() if k.isupper() and not k.startswith("_")}
    problems = [f"missing in EN: {k}" for k in sorted(pl_names - en_names)]
    problems += [f"only in EN: {k}" for k in sorted(en_names - pl_names)]
    not_templates = {"SYNTAX_PREFAB_JSON"}          # nawiasy klamrowe to przykład formatu .et, nie pola .format()
    for k in sorted((pl_names & en_names) - not_templates):
        if _fields(getattr(_pl, k)) != _fields(globals()[k]):
            problems.append(f"different fields in {k}: {_fields(getattr(_pl, k))} vs {_fields(globals()[k])}")
    print("\n".join(problems) or f"OK: {len(en_names)} constants, same names and fields")
    sys.exit(1 if problems else 0)
