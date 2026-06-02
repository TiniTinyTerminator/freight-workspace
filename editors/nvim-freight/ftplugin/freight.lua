vim.bo.commentstring = "# %s"

if vim.g.freight_lsp_auto_start ~= false then
  require("freight").start()
end
