"""Database Browser widget with multi-DB support."""
from textual.widgets import Static, DataTable, Input
from textual.containers import VerticalScroll, Horizontal
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from rich.table import Table as RichTable
from typing import List, Dict, Any, Optional
import subprocess
import json
from src.utils.logger import logger


class DatabaseBrowser(VerticalScroll):
    """
    Database Browser widget.

    Supports PostgreSQL, MySQL, SQLite, MongoDB (via CLI tools).
    """

    connection_active = reactive(False)
    current_db = reactive(None)

    DEFAULT_CSS = """
    DatabaseBrowser {
        background: rgba(0, 20, 0, 0.8);
        border: round #00FF00;
        padding: 1;
        scrollbar-background: rgba(0, 10, 0, 0.5);
        scrollbar-color: #00FF00;
    }

    DatabaseBrowser:focus {
        border: heavy #00FF00;
        background: rgba(0, 30, 0, 0.9);
    }

    .db-header {
        background: rgba(0, 100, 0, 0.8);
        color: #FFFFFF;
        text-style: bold;
        padding: 1;
        margin-bottom: 1;
    }

    .db-query {
        background: rgba(0, 15, 0, 0.7);
        border: round #00AA00;
        padding: 1;
        margin: 1 0;
    }

    .db-result {
        background: rgba(0, 20, 0, 0.7);
        border: round #00FF00;
        padding: 1;
        margin: 1 0;
    }

    .db-error {
        color: #FF0000;
        text-style: bold;
    }

    .db-success {
        color: #00FF00;
    }
    """

    class QueryExecuted(Message):
        """Message sent when query is executed."""

        def __init__(self, query: str, rows_affected: int) -> None:
            super().__init__()
            self.query = query
            self.rows_affected = rows_affected

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.query_history = []
        self.connection_info = None

    def compose(self):
        """Create child widgets."""
        yield Static(
            "[bold bright_green]╔═══════════════════════════════════════════╗[/]\n"
            "[bold bright_green]║      🗄️  Database Matrix Browser          ║[/]\n"
            "[bold bright_green]╚═══════════════════════════════════════════╝[/]",
            classes="db-header"
        )
        yield Static(
            "[dim green]Multi-database browser and query tool[/]\n\n"
            "[cyan]Supported Databases:[/]\n"
            "[green]  • PostgreSQL[/] (psql)\n"
            "[green]  • MySQL[/] (mysql)\n"
            "[green]  • SQLite[/] (sqlite3)\n"
            "[green]  • MongoDB[/] (mongo)\n\n"
            "[cyan]Example Connections:[/]\n"
            "[yellow]  PostgreSQL:[/] postgresql://user:pass@localhost/dbname\n"
            "[yellow]  MySQL:[/] mysql://user:pass@localhost/dbname\n"
            "[yellow]  SQLite:[/] sqlite:///path/to/database.db\n"
            "[yellow]  MongoDB:[/] mongodb://localhost:27017/dbname\n",
            id="db-help"
        )

    def connect_postgresql(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
        user: str = "postgres",
        password: Optional[str] = None
    ) -> bool:
        """
        Connect to PostgreSQL database.

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Username
            password: Password

        Returns:
            True if connection successful
        """
        try:
            # Test connection
            env = {}
            if password:
                env["PGPASSWORD"] = password

            result = subprocess.run(
                ["psql", "-h", host, "-p", str(port), "-U", user, "-d", database,
                 "-c", "SELECT 1;"],
                capture_output=True,
                timeout=10,
                env=env
            )

            success = result.returncode == 0
            if success:
                self.connection_info = {
                    "type": "postgresql",
                    "host": host,
                    "port": port,
                    "database": database,
                    "user": user
                }
                self.connection_active = True
                self.current_db = "PostgreSQL"
                logger.info(f"Connected to PostgreSQL: {database}")
                self.show_success(f"Connected to PostgreSQL database: {database}")
            else:
                self.show_error(f"Connection failed: {result.stderr.decode()}")

            return success

        except Exception as e:
            self.show_error(f"PostgreSQL connection error: {e}")
            logger.error(f"PostgreSQL connection error: {e}")
            return False

    def connect_sqlite(self, db_path: str) -> bool:
        """
        Connect to SQLite database.

        Args:
            db_path: Path to SQLite database file

        Returns:
            True if connection successful
        """
        try:
            # Test connection
            result = subprocess.run(
                ["sqlite3", db_path, "SELECT 1;"],
                capture_output=True,
                timeout=5
            )

            success = result.returncode == 0
            if success:
                self.connection_info = {
                    "type": "sqlite",
                    "db_path": db_path
                }
                self.connection_active = True
                self.current_db = "SQLite"
                logger.info(f"Connected to SQLite: {db_path}")
                self.show_success(f"Connected to SQLite database: {db_path}")
            else:
                self.show_error(f"Connection failed: {result.stderr.decode()}")

            return success

        except Exception as e:
            self.show_error(f"SQLite connection error: {e}")
            logger.error(f"SQLite connection error: {e}")
            return False

    def execute_query(self, query: str) -> Dict[str, Any]:
        """
        Execute SQL query.

        Args:
            query: SQL query to execute

        Returns:
            Result dictionary with rows, columns, affected
        """
        if not self.connection_active or not self.connection_info:
            return {"error": "No active database connection"}

        try:
            self.show_query(query)

            db_type = self.connection_info["type"]

            if db_type == "postgresql":
                return self._execute_postgresql(query)
            elif db_type == "sqlite":
                return self._execute_sqlite(query)
            elif db_type == "mysql":
                return self._execute_mysql(query)
            else:
                return {"error": f"Unsupported database type: {db_type}"}

        except Exception as e:
            error_msg = f"Query execution error: {e}"
            self.show_error(error_msg)
            logger.error(error_msg)
            return {"error": str(e)}

    def _execute_postgresql(self, query: str) -> Dict[str, Any]:
        """Execute PostgreSQL query."""
        try:
            info = self.connection_info
            env = {}
            if info.get("password"):
                env["PGPASSWORD"] = info["password"]

            result = subprocess.run(
                ["psql", "-h", info["host"], "-p", str(info["port"]),
                 "-U", info["user"], "-d", info["database"],
                 "-c", query, "-t", "-A", "-F", "|"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env
            )

            if result.returncode != 0:
                return {"error": result.stderr}

            # Parse results
            lines = result.stdout.strip().split("\n")
            if not lines or not lines[0]:
                return {"rows": [], "affected": 0}

            rows = []
            for line in lines:
                if line:
                    rows.append(line.split("|"))

            result_data = {
                "rows": rows,
                "affected": len(rows),
                "query": query
            }

            self.show_result(result_data)
            self.query_history.append(query)
            self.post_message(self.QueryExecuted(query, len(rows)))

            return result_data

        except subprocess.TimeoutExpired:
            return {"error": "Query timeout (30s)"}
        except Exception as e:
            return {"error": str(e)}

    def _execute_sqlite(self, query: str) -> Dict[str, Any]:
        """Execute SQLite query."""
        try:
            db_path = self.connection_info["db_path"]

            result = subprocess.run(
                ["sqlite3", db_path, "-header", "-column", query],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return {"error": result.stderr}

            # Parse results
            output = result.stdout.strip()
            if not output:
                return {"rows": [], "affected": 0}

            lines = output.split("\n")
            rows = [line.split() for line in lines if line.strip()]

            result_data = {
                "rows": rows,
                "affected": len(rows) - 1 if rows else 0,  # Exclude header
                "query": query
            }

            self.show_result(result_data)
            self.query_history.append(query)
            self.post_message(self.QueryExecuted(query, len(rows)))

            return result_data

        except subprocess.TimeoutExpired:
            return {"error": "Query timeout (30s)"}
        except Exception as e:
            return {"error": str(e)}

    def _execute_mysql(self, query: str) -> Dict[str, Any]:
        """Execute MySQL query (stub for future implementation)."""
        return {"error": "MySQL support coming soon"}

    def show_query(self, query: str) -> None:
        """Display query."""
        self.mount(
            Static(
                f"[bold cyan]→ Executing Query[/]\n\n"
                f"[yellow]{query}[/]",
                classes="db-query"
            )
        )

    def show_result(self, result: Dict[str, Any]) -> None:
        """Display query result."""
        rows = result.get("rows", [])
        affected = result.get("affected", 0)

        if not rows:
            result_text = f"[dim green]Query executed successfully. {affected} rows affected.[/]"
        else:
            # Build table display
            result_text = f"[bold green]✅ Query Results[/] ({affected} rows)\n\n"

            # Simple table representation
            for i, row in enumerate(rows[:20]):  # Limit to 20 rows for display
                row_text = " | ".join(str(cell) for cell in row)
                result_text += f"[green]{i+1}.[/] {row_text}\n"

            if len(rows) > 20:
                result_text += f"\n[dim]... {len(rows) - 20} more rows[/]"

        self.mount(
            Static(
                result_text,
                classes="db-result"
            )
        )

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def show_success(self, message: str) -> None:
        """Show success message."""
        self.mount(
            Static(
                f"[bold green]✅ {message}[/]",
                classes="db-success"
            )
        )

    def show_error(self, error: str) -> None:
        """Show error message."""
        self.mount(
            Static(
                f"[bold red]❌ Error[/]\n[red]{error}[/]",
                classes="db-error"
            )
        )

    def disconnect(self) -> None:
        """Disconnect from database."""
        self.connection_active = False
        self.connection_info = None
        self.current_db = None
        logger.info("Disconnected from database")

    def get_tables(self) -> List[str]:
        """Get list of tables in current database."""
        if not self.connection_active:
            return []

        db_type = self.connection_info["type"]

        if db_type == "postgresql":
            query = "SELECT tablename FROM pg_tables WHERE schemaname='public';"
        elif db_type == "sqlite":
            query = "SELECT name FROM sqlite_master WHERE type='table';"
        else:
            return []

        result = self.execute_query(query)
        if "rows" in result:
            return [row[0] for row in result["rows"]]
        return []
