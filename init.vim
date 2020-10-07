" ----------------------------------------
" NeoVim Config
" ----------------------------------------


" ----------------------------------------
"  Plugins
" ----------------------------------------

call plug#begin('/home/user/.config/nvim/bundle')

Plug 'sheerun/vim-polyglot'
Plug 'vim-airline/vim-airline' 											" Airline
Plug 'vim-airline/vim-airline-themes' 									" Airline Color Schemes
Plug 'dracula/vim', { 'name': 'dracula' } 								" Dracula Color Scheme
Plug 'kovetskiy/sxhkd-vim' 												" sxhkd Syntax Highlighting
Plug 'vim-python/python-syntax' 										" Python Syntax Highlighting
Plug 'dag/vim-fish' 													" Fish Syntax Highlighting
Plug 'scrooloose/nerdtree'                              				" NERDree File Explorer
Plug 'tiagofumo/vim-nerdtree-syntax-highlight' 							" NERDTree Syntax Highlighting
Plug 'ryanoasis/vim-devicons' 											" Filetype Icons
Plug 'suan/vim-instant-markdown', {'for': 'markdown'} 					" Markdown Browser Previews
Plug 'rrethy/vim-hexokinase', { 'do': 'make hexokinase' } 				" Color Value Previews
Plug 'vimwiki/vimwiki' 													" Vim Wiki
Plug 'preservim/nerdcommenter' 											" Code Commenter
Plug 'mileszs/ack.vim' 													" Ack File Searches
Plug 'tpope/vim-surround'                           					" Change surrounding marks
Plug 'frazrepo/vim-rainbow'
Plug 'airblade/vim-gitgutter' 											" Git Differences in Gutter
Plug 'jreybert/vimagit'
Plug 'scrooloose/syntastic'
Plug 'zchee/deoplete-jedi'
Plug 'godlygeek/tabular'

"Plug 'neoclide/coc.nvim', {'branch': 'release'} 						" Auto Completions
"Plug 'w0rp/ale'
"Plug 'junegunn/fzf', { 'dir': '~/.config/fzf', 'do': './install --all' }			" Fuzzy finder

call plug#end()

" ----------------------------------------
"  Plugin Settings
" ----------------------------------------

let g:deoplete#sources#jedi#ignore_errors = 1

"  Airline
let g:airline_theme = "dracula"														" Set airline theme
let g:airline_powerline_fonts = 0													" Disable Powerline Fonts

" Hexokinase
let g:Hexokinase_highlighters = ["backgroundfull"] 									" Show Colors as Background of Value
let g:Hexokinase_refreshEvents = [ "BufRead", "BufWrite", "InsertLeave" ] 			" Refresh Colors on Open, Save and Quit

" Instant Markdown
let g:instant_markdown_autostart = 1
let g:instant_markdown_allow_unsafe_content = 1

" NERDTree
let g:NERDTreeQuitOnOpen=1 															" Close NERDTree on File Open
let g:NERDTreeMapOpenInTab='<ENTER>' 												" Open Files in New Tab
let g:NERDTreeHijackNetrw = 1 														" xxx
let g:NERDTreeAutoDeleteBuffer = 1 													" Delete Corresponding Buffer When File Is Deleted
"let g:NERDTreeStatusline="%{matchstr(getline('.'), '\\s\\zs\\w\\(.*\\)')}"

"let NERDTreeMinimalUI = 0
"let NERDTreeDirArrows = 1

" Python Syntax Highlighting
let g:python_highlight_all = 1

" NERD Commenter
let g:NERDSpaceDelims = 1 															" Add a Space After Comment Delimiters

" Vim Rainbow
let g:rainbow_active = 1

" Vimwiki
let g:vimwiki_list = [{"path": "~/.config/nvim/vimwiki/", "syntax": "markdown", "ext": ".md"}]


" ----------------------------------------
"  Sections
" ----------------------------------------

set showtabline=1											" Enable Tabline if Multiple Tabs Exist
set laststatus=2											" Enable Status Line
set noshowmode												" Disable Default Mode Line
set signcolumn=yes 											" Enable Sign Column
set relativenumber number 									" Enable Relative Line Numbers, Standard Line Numbers
set cmdheight=1 											" Set Command Line Height to One Row
set hidden 													" Hide unloaded buffer instead of abandoning it


" ----------------------------------------
"  Appearance
" ----------------------------------------

syntax enable												" Enable Syntax Highlighting (Do Not Override Custom Settings)
set termguicolors 											" Enable 24-bit RGB Color (Use gui color attributes Over cterm)
colorscheme dracula 										" Set colorscheme to dracula
highlight Normal guifg=#FFFFFF guibg=#000000 				" Set Background Color to Black
highlight clear SignColumn 									" Set gutter color to nothing


" ----------------------------------------
"  Behavior
" ----------------------------------------

filetype plugin indent on									" Enable Filetype Detection, Plugin Handling and Indentation
set scrolloff=22 											" Vertical Scroll Padding Rows
set mouse=a 												" Enable mouse support (in all modes)
set switchbuf=useopen,usetab,newtab 						" Buffer Switching Behavior
set foldmethod=manual 										" Set Folding to Manual
set timeoutlen=1000 ttimeoutlen=0							" Key sequence delay
"set lazyredraw												" Don't redraw screen while executing macros, registers and other commands
set noerrorbells											" Disable error bell
set novisualbell											" Disable visual bell
set pyxversion=3
set history=1000  											" Set history tables memory to 500 lines
set backspace=eol,start,indent								" Configure backspace so it acts as it should act


" ----------------------------------------
"  Indentation, Wrapping, Tabs and Spaces
" ----------------------------------------

set autoindent 												" Use indentation from previous line
set expandtab 											" Disable replacing of tabs with spaces
set tabstop=4												" Number of spaces that a tab counts for
set textwidth=0												" Disable line character limit
set shiftwidth=4
set whichwrap+=<,>,h,l										" Configure arrow keys to wrap to next line
set nowrap													" Disable line wrapping
set nolinebreak												" Disable line breaks
"set cindent
set smartindent
set nosmarttab


" ------------------------------
"  Files
" ------------------------------

set fileformats=unix,dos,mac								" Attempt unix, dos and mac for File Formats in That Order
set fileencodings=utf8,cp1252,latin1										" Set File Encoding to UTF-8
set encoding=utf8											" Set UTF-8 as standard encoding
set autoread												" Enable auto-read when a file is changed from the outside
set autochdir												" Change directory to working file
set nowriteany												" Disable Write to any file regardless of owner/permissions
set nobackup												" Disable write backup when overwriting a file that is kept after writing
set nowritebackup											" Disable write backup when overwriting a file
set swapfile												" Enable swap filefor buffers


" ------------------------------
"  Searches
" ------------------------------

set ignorecase														" Ignore case when searching
set smartcase														" When searching try to be smart about cases
set hlsearch														" Highlight search results
set incsearch														" Enable find matches as typing search string
set showmatch														" Enable highlight matching brackets
set matchtime=2														" Tenths of a second to blink when matching brackets
set magic															" Enable looser regular expressions


" ------------------------------
"  Wild Menus
" ------------------------------

set wildmenu														" Enable menu auto-completion (wildmenu)
set wildignore=*.o,*~,*.pyc											" Ignore matching files
set wildignore+=*/.git/*,*/.hg/*,*/.svn/*,*/.DS_Store				" Ignore compiled files


" ------------------------------
"  Automated Commands
" ------------------------------

" Jump to Last Edited Line on Load
autocmd BufReadPost * if line("'\"") > 1 && line("'\"") <= line("$") | exe "normal! g'\"" | endif

" Clean Trailing Whitespaces
autocmd BufWritePre *.yml,*.yaml,*.conf,*.cfg,*.txt,*.js,*.json,*.py,*.wiki,*.sh,*.vim,*.coffee,vimrc,nanorc,neomuttrc :call CleanTrailingWhitespace()

" Reload init.vim on Save
autocmd BufWritePost init.vim source %

" Open NERDTree if No File Specified
autocmd StdinReadPre * let s:std_in=1
autocmd VimEnter * if argc() == 0 && !exists("s:std_in") | NERDTree | endif


" ------------------------------
"  Helper Functions
" ------------------------------

" Delete trailing white space on save, useful for some filetypes
fun! CleanTrailingWhitespace()
    let save_cursor = getpos(".")
    let old_query = getreg('/')
    silent! %s/\s\+$//e
    call setpos('.', save_cursor)
    call setreg('/', old_query)
endfun

" Select Word Under Cursor and Search for It
function! VisualSelection(direction, extra_filter) range
    let l:saved_reg = @"
    execute "normal! vgvy"

    let l:pattern = escape(@", "\\/.*'$^~[]")
    let l:pattern = substitute(l:pattern, "\n$", "", "")

    if a:direction == 'gv'
        call CmdLine("Ack '" . l:pattern . "' " )
    elseif a:direction == 'replace'
        call CmdLine("%s" . '/'. l:pattern . '/')
    endif

    let @/ = l:pattern
    let @" = l:saved_reg
endfunction

function! CmdLine(str)
    call feedkeys(":" . a:str)
endfunction


" ------------------------------
"  Keybindings
" ------------------------------

let mapleader = "\\"

nmap <C-j> :NERDCommenterToggle<CR>

" <Space> Search Forward
noremap <space> /

" <Control-Space> Search Reverse
noremap <C-space> ?

" <Control-z> Clear Search Highlighting
noremap <C-z> :nohlsearch<CR>

" <Control-c> Close the current tab
noremap <C-c> :close<CR>

" <Control-q> Quit
noremap <C-q> :quit<CR>

" <Control-n> Toggle NERDTree
noremap <C-n> :NERDTreeToggle<CR>

" <Control-w> Jump Between Tabs/Buffers
noremap <C-w> :wincmd w<CR>

" <Control-[> Move to Previous Tab
noremap <C-[> :tabprevious<CR>

" <Control-]> Move to Next Tab
noremap <C-]> :tabnext<CR>

" <Control-a> Save File As
noremap <C-a> :saveas <c-r>=expand("%:p:h")<CR>/

" <Shift-*> Search Forward for Word Under Cursor
vnoremap <silent> * :<C-u>call VisualSelection('', '')<CR>/<C-R>=@/<CR><CR>

" <Shift-#> Search in Reverse for Word Under Cursor
vnoremap <silent> # :<C-u>call VisualSelection('', '')<CR>?<C-R>=@/<CR><CR>

" <Control-o> Open <filename> in New Tab
noremap <C-o> :tabedit<space>

" <Control-e> Open <filename> from Current Folder in New Tab
noremap <C-e> :tabedit <c-r>=expand("%:p:h")<CR>/

" Enable Up/Down Arrows in Wildmenu
if &wildoptions =~ "pum"
    cnoremap <expr> <up> pumvisible() ? "<C-p>" : "\\<up>"
    cnoremap <expr> <down> pumvisible() ? "<C-n>" : "\\<down>"
endif

" Open Common Configuration Files
nnoremap <leader>1 :tabedit ~/.config/vim/vimrc<CR>
nnoremap <leader>2 :tabedit ~/.config/zsh/.zshrc<CR>
nnoremap <leader>3 :tabedit ~/.config/bspwm/bspwmrc<CR>
nnoremap <leader>4 :tabedit ~/.config/sxhkd/sxhkdrc<CR>
nnoremap <leader>5 :tabedit ~/.config/polybar/config.ini<CR>
nnoremap <leader>6 :tabedit ~/.config/neomutt/neomuttrc<CR>
