local M = {}

local defaults = {
  freight = "freight",
  profile = "dev",
  clangd = "clangd",
  fortls = "fortls",
  asm_lsp = "asm-lsp",
  enable_clangd = true,
  enable_fortls = true,
  enable_asm_lsp = true,
}

local config = vim.deepcopy(defaults)
local augroup = vim.api.nvim_create_augroup("freight.nvim", { clear = true })

local source_patterns = {
  "*.c",
  "*.h",
  "*.cc",
  "*.hh",
  "*.cpp",
  "*.hpp",
  "*.cxx",
  "*.hxx",
  "*.cppm",
  "*.ixx",
  "*.mpp",
  "*.cu",
  "*.cuh",
  "*.hip",
  "*.m",
  "*.mm",
  "*.f",
  "*.for",
  "*.f90",
  "*.f95",
  "*.f03",
  "*.f08",
  "*.asm",
  "*.nasm",
  "*.s",
  "*.S",
  "freight.toml",
}

local function root_dir(start)
  local found = vim.fs.find("freight.toml", {
    upward = true,
    path = start or vim.api.nvim_buf_get_name(0),
  })[1]
  return found and vim.fs.dirname(found) or nil
end

local function lsp_cmd()
  local cmd = {
    config.freight,
    "lsp",
    "--profile",
    config.profile,
    "--clangd",
    config.clangd,
    "--fortls",
    config.fortls,
    "--asm-lsp",
    config.asm_lsp,
  }

  if not config.enable_clangd then
    table.insert(cmd, "--no-clangd")
  end
  if not config.enable_fortls then
    table.insert(cmd, "--no-fortls")
  end
  if not config.enable_asm_lsp then
    table.insert(cmd, "--no-asm-lsp")
  end

  return cmd
end

local function notify_manifest_changed(client, file)
  if not client then
    return
  end
  client.notify("workspace/didChangeWatchedFiles", {
    changes = {
      {
        uri = vim.uri_from_fname(file),
        type = 2,
      },
    },
  })
end

local function attach_manifest_watch(client, root)
  vim.api.nvim_clear_autocmds({
    group = augroup,
    pattern = root .. "/freight.toml",
  })
  vim.api.nvim_create_autocmd({ "BufWritePost" }, {
    group = augroup,
    pattern = root .. "/freight.toml",
    callback = function(event)
      notify_manifest_changed(client, event.file)
    end,
  })
end

function M.start()
  local root = root_dir()
  if not root then
    return nil
  end

  for _, client in ipairs(vim.lsp.get_clients({ name = "freight" })) do
    if client.config.root_dir == root then
      vim.lsp.buf_attach_client(0, client.id)
      return client.id
    end
  end

  local id = vim.lsp.start({
    name = "freight",
    cmd = lsp_cmd(),
    root_dir = root,
    on_attach = function(client)
      attach_manifest_watch(client, root)
    end,
  })

  return id
end

local function autocmd_pattern()
  local patterns = {}
  for _, pattern in ipairs(source_patterns) do
    table.insert(patterns, "**/" .. pattern)
  end
  return patterns
end

function M.stop()
  for _, client in ipairs(vim.lsp.get_clients({ name = "freight" })) do
    client.stop()
  end
end

function M.restart()
  M.stop()
  vim.defer_fn(M.start, 100)
end

local function run(args)
  local root = root_dir()
  if not root then
    vim.notify("No freight.toml found", vim.log.levels.ERROR)
    return
  end
  local words = vim.tbl_map(vim.fn.shellescape, vim.list_extend({ config.freight }, args))
  local command = table.concat(words, " ")
  vim.cmd("terminal cd " .. vim.fn.fnameescape(root) .. " && " .. command)
end

local function create_commands()
  vim.api.nvim_create_user_command("FreightBuild", function(opts)
    run(vim.list_extend({ "build" }, opts.fargs))
  end, { nargs = "*" })

  vim.api.nvim_create_user_command("FreightRun", function(opts)
    run(vim.list_extend({ "run" }, opts.fargs))
  end, { nargs = "*" })

  vim.api.nvim_create_user_command("FreightTest", function(opts)
    run(vim.list_extend({ "test" }, opts.fargs))
  end, { nargs = "*" })

  vim.api.nvim_create_user_command("FreightFetch", function(opts)
    run(vim.list_extend({ "fetch" }, opts.fargs))
  end, { nargs = "*" })

  vim.api.nvim_create_user_command("FreightClean", function()
    run({ "clean" })
  end, {})

  vim.api.nvim_create_user_command("FreightCompileCommands", function()
    run({ "compile-commands" })
  end, {})

  vim.api.nvim_create_user_command("FreightRestartLsp", function()
    M.restart()
  end, {})
end

function M.setup(opts)
  config = vim.tbl_deep_extend("force", vim.deepcopy(defaults), opts or {})
  create_commands()
  vim.api.nvim_create_autocmd({ "BufReadPost", "BufNewFile" }, {
    group = augroup,
    pattern = autocmd_pattern(),
    callback = function()
      M.start()
    end,
  })
  M.start()
end

return M
