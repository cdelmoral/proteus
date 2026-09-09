return {
  {
    "stevearc/oil.nvim",
    opts = {
      columns = { "icon", "permissions", "size", "mtime" },
      delete_to_trash = true,
      view_options = { show_hidden = true },
      constrain_cursor = "name",
    },
    dependencies = { { "nvim-mini/mini.icons", opts = {} } },
  },
  {
    "ibhagwan/fzf-lua",
    keys = {
      { "<leader><space>", LazyVim.pick("files", { root = false }), desc = "Find Files" },
    },
  },
}
