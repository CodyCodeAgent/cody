"""CLI interface for Cody"""

import click
from rich.console import Console
from rich.markdown import Markdown

console = Console()


@click.command()
@click.argument('prompt', required=False)
@click.option('--model', default='claude-3-5-sonnet-20241022', help='AI model to use')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.version_option()
def main(prompt, model, verbose):
    """
    🤖 Cody - Your AI coding companion
    
    Examples:
        cody "write a hello world function"
        cody "explain this code" < file.py
    """
    if not prompt:
        console.print("[yellow]Welcome to Cody! 🤖[/yellow]")
        console.print("Usage: cody 'your question or task'")
        return
    
    if verbose:
        console.print(f"[dim]Using model: {model}[/dim]")
    
    # TODO: Implement AI interaction
    console.print(f"[green]Received:[/green] {prompt}")
    console.print("[yellow]AI interaction coming soon...[/yellow]")


if __name__ == '__main__':
    main()
