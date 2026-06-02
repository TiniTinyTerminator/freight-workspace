# nvim-freight

Minimal Neovim integration for Freight projects.

## Features

- Detects `freight.toml` as `freight`.
- Starts `freight lsp` with Neovim's built-in LSP client.
- Watches `freight.toml` and notifies the server when the manifest changes, so
  `compile_commands.json` is refreshed after package additions.
- Provides user commands for common Freight workflows.

## Install With lazy.nvim

```lua
{
  dir = "/path/to/freight/editors/nvim-freight",
  ft = { "freight" },
  config = function()
    require("freight").setup({
      freight = "freight",
      profile = "dev",
      clangd = "clangd",
      fortls = "fortls",
      asm_lsp = "asm-lsp",
    })
  end,
}
```

For a normal plugin repository, replace `dir = ...` with the repository name.

## Commands

- `:FreightBuild`
- `:FreightRun`
- `:FreightTest`
- `:FreightFetch`
- `:FreightClean`
- `:FreightCompileCommands`
- `:FreightRestartLsp`

Commands run from the nearest directory containing `freight.toml`.
