vim.opt.diffopt:remove("linematch:40")
vim.opt.diffopt:append({ "linematch:60", "algorithm:histogram", "indent-heuristic" })
vim.g.lazyvim_prettier_needs_config = true
