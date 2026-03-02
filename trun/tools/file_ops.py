"""
File operations tool.
"""

import os
from glob import glob
from pathlib import Path
from typing import Any


class FileOpsTool:
    """Tool for file operations."""

    def read_file(self, path: str, encoding: str = "utf-8") -> dict[str, Any]:
        """
        Read file content.

        :param path: File path
        :param encoding: File encoding
        :return: {"success": bool, "content": str, "error": str}
        """
        try:
            with open(path, 'r', encoding=encoding) as f:
                return {"success": True, "content": f.read()}
        except FileNotFoundError:
            return {"success": False, "error": f"File not found: {path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, path: str, content: str, encoding: str = "utf-8") -> dict[str, Any]:
        """
        Write content to file.

        :param path: File path
        :param content: Content to write
        :param encoding: File encoding
        :return: {"success": bool, "error": str}
        """
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, 'w', encoding=encoding) as f:
                f.write(content)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def append_file(self, path: str, content: str, encoding: str = "utf-8") -> dict[str, Any]:
        """
        Append content to file.

        :param path: File path
        :param content: Content to append
        :param encoding: File encoding
        :return: {"success": bool, "error": str}
        """
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, 'a', encoding=encoding) as f:
                f.write(content)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def file_exists(self, path: str) -> bool:
        """
        Check if file exists.

        :param path: File path
        :return: True if file exists
        """
        return os.path.exists(path)

    def list_files(self, directory: str, pattern: str = "*") -> list[str]:
        """
        List files in directory matching pattern.

        :param directory: Directory path
        :param pattern: Glob pattern
        :return: List of file paths
        """
        full_pattern = os.path.join(directory, pattern)
        return glob(full_pattern)

    def delete_file(self, path: str) -> dict[str, Any]:
        """
        Delete a file.

        :param path: File path
        :return: {"success": bool, "error": str}
        """
        try:
            os.remove(path)
            return {"success": True}
        except FileNotFoundError:
            return {"success": False, "error": f"File not found: {path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_directory(self, path: str) -> dict[str, Any]:
        """
        Create directory (including parents).

        :param path: Directory path
        :return: {"success": bool, "error": str}
        """
        try:
            os.makedirs(path, exist_ok=True)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
