# Problems

[ ] - Duplicate nodes generated for classes (one a (Class), other (Class & Symbol))
        - Class & Symbol
            - Has link to file node
                - Has link to (function & symbol) node
                 - Has all properties
            - Has all properties (name, line, type etc.)
        - Class
            - Has link to (function) node w/ cluster
                - Missing properties
            - Missing properties
    Why are we seeing this error? It seems like where we are missing the symbol node it is because we are creating a class and possibly function from an import
    Also it seems like we are seeing the symbol nodes not linking class methods to their classes.
    See src/code_index_mcp/indexing/problem_classes.csv
[ ] {
  "method": "notifications/message",
  "params": {
    "level": "info",
    "logger": "stdio",
    "data": {
      "message": "2025-09-28 02:31:31,108 - code_index_mcp.indexing.models.import_call_info - WARNING - No module named 'vertex_eval'\nTraceback (most recent call last):\n  File \"/Users/conor.fehilly/Documents/repos/code-index-mcp/src/code_index_mcp/indexing/models/import_call_info.py\", line 31, in get_import_spec\n    spec = PathFinder.find_spec(import_fullname) or PathFinder.find_spec(import_fullname, path) or find_spec(import_fullname)\n                                                                                                   ^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"<frozen importlib.util>\", line 94, in find_spec\nModuleNotFoundError: No module named 'vertex_eval'"
    }
  }
}