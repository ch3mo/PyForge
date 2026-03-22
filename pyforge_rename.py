"""Rename a Python identifier across project files (rope if available, else AST)."""
import ast
import os
import re


def _walk_py(project_root, skip_dirs):
    for r, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(r, f)


def _ast_rename_file(src, old_name, new_name):
    if old_name == new_name or not old_name.isidentifier():
        return src, 0
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None, 0

    class V(ast.NodeTransformer):
        def __init__(self):
            self.n = 0

        def visit_Name(self, node):
            if node.id == old_name:
                self.n += 1
                return ast.copy_location(ast.Name(id=new_name, ctx=node.ctx), node)
            return node

        def visit_arg(self, node):
            if node.arg == old_name:
                self.n += 1
                node = ast.copy_location(ast.arg(arg=new_name, annotation=node.annotation), node)
            return self.generic_visit(node)

        def visit_FunctionDef(self, node):
            if node.name == old_name:
                self.n += 1
                node = node._replace(name=new_name)
            return self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            return self.visit_FunctionDef(node)

        def visit_ClassDef(self, node):
            if node.name == old_name:
                self.n += 1
                node = node._replace(name=new_name)
            return self.generic_visit(node)

    v = V()
    new_tree = v.visit(tree)
    ast.fix_missing_locations(new_tree)
    try:
        out = ast.unparse(new_tree)
    except AttributeError:
        return None, 0
    return out, v.n


def _rope_rename_project(project_root, old_name, new_name, skip_dirs):
    from rope.base.project import Project
    from rope.refactor.rename import Rename

    proj = Project(project_root)
    for path in _walk_py(project_root, skip_dirs):
        rel = os.path.relpath(path, project_root).replace("\\", "/")
        res = proj.get_resource(rel)
        if not res.exists():
            continue
        src = res.read()
        m = re.search(r"\b" + re.escape(old_name) + r"\b", src)
        if not m:
            continue
        renamer = Rename(proj, res, m.start())
        changes = renamer.get_changes(new_name)
        proj.do(changes)
        return True
    return False


def rename_symbol_project(project_root, old_name, new_name, skip_dirs=None):
    """
    Returns (files_changed, total_replacements, message).
    """
    skip_dirs = skip_dirs or {"__pycache__", ".git", ".venv", "venv", "node_modules", "build", "dist", ".idea"}
    if not old_name:
        return 0, 0, "Invalid name."
    if old_name != new_name and not new_name.isidentifier():
        return 0, 0, "Invalid new name."

    try:
        if _rope_rename_project(project_root, old_name, new_name, skip_dirs):
            return -1, -1, "Renamed with rope (project-wide)."
    except Exception:
        pass

    total_rep = 0
    files_changed = 0
    for path in _walk_py(project_root, skip_dirs):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read()
        except OSError:
            continue
        out, n = _ast_rename_file(src, old_name, new_name)
        if out is None or n == 0:
            continue
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(out)
        except OSError:
            continue
        files_changed += 1
        total_rep += n

    if files_changed == 0:
        return 0, 0, "No changes (check the symbol name; install rope for smarter refactors)."
    return files_changed, total_rep, f"AST rename: {files_changed} file(s), {total_rep} node(s)."
