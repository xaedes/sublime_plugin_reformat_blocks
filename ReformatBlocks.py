import sublime
import sublime_plugin
import re
s = sublime.load_settings("ReformatBlocks.sublime-settings")

class Token:
    token_type = None
    start      = None
    end        = None
    string     = None

    def __init__(self, token_type, start, end, string=None):
        self.token_type = token_type
        self.start = start
        self.end = end
        self.string = string

    def length(self):
        return self.end - self.start

    def as_text(self, text):
        return text[self.start:self.end] if self.string is None else self.string

class Block:
    blk_id      = None
    open_token  = None
    close_token = None
    parent      = None
    start       = None
    end         = None
    depth       = None
    children    = []
    separators  = []

    def __init__(self, blk_id = None, open_token = None, close_token = None, parent = None, start = None, end = None, depth = None):
        self.blk_id      = blk_id
        self.open_token  = open_token
        self.close_token = close_token
        self.parent      = parent
        self.start       = start
        self.end         = end
        self.depth       = depth
        self.children    = []
        self.separators  = []

        self.depth = 0 if self.parent is None else (self.parent.depth+1)
    def length(self):
        return self.end + 1 - self.start
    
    def content_length(self):
        return self.length() - 2

    def __str__(self):
        return str((self.blk_id, self.open_token, self.close_token, self.parent, self.start, self.end, self.depth, self.children))

class Params:
    def __init__(self, s):
        self.min_content_length = s.get("min_content_length", 1   )
        self.min_seperators     = s.get("min_seperators",     1   )
        self.indent             = s.get("indent",             4   )

params = Params(s)

class ReformatFoldBlocksCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        regions = self.view.sel()
        for region in regions:
            selection, selected_entire_file = Formatter.get_selection_from_region(
                region=region, regions_length=len(regions), view=self.view
            )
            if selection is None:
                continue

            selection_text = self.view.substr(selection)
            self.view.replace(edit, selection, Formatter.replace_text(selection_text, -1))

class ReformatUnfoldBlocksCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        regions = self.view.sel()
        for region in regions:
            selection, selected_entire_file = Formatter.get_selection_from_region(
                region=region, regions_length=len(regions), view=self.view
            )
            if selection is None:
                continue

            selection_text = self.view.substr(selection)
            self.view.replace(edit, selection, Formatter.replace_text(selection_text, +1))


class Formatter:
    @staticmethod
    def replace_text(text, fold_direction):

        token_patterns = ["<",">","(",")","{","}","[","]","\n",",","="]
        default_token_char = "t"
        token_chars = ["<",">","(",")","{","}","[","]"," ",",","="]

        direction = fold_direction
        
        indent_str = " " * params.indent

        token_list = Formatter.build_token_list(text, token_patterns, -1)
        token_list = Formatter.fold_all(text, token_list)

        token_string = Formatter.build_token_string(token_list, token_chars, default_token_char)

        blocks = Formatter.build_blocks(token_string)
        depths = Formatter.build_depths(blocks, len(token_string))
        actual_max_depth = max(depths)+1

        
        max_depth = 0
        if direction > 0:
            for max_depth in range(actual_max_depth):
                reformated = Formatter.reformat_text(
                    text, blocks, token_list, token_string, depths, token_chars,
                    token_patterns, indent_str, default_token_char, max_depth
                )
                if text == reformated:
                    reformated = Formatter.reformat_text(
                        text, blocks, token_list, token_string, depths, token_chars,
                        token_patterns, indent_str, default_token_char, max_depth+1
                    )
                    if text == reformated: break
                    return reformated
                if len(reformated) > len(text):
                    # it will only get longer
                    reformated = Formatter.reformat_text(
                        text, blocks, token_list, token_string, depths, token_chars,
                        token_patterns, indent_str, default_token_char, max_depth
                    )
                    if text == reformated: break
                    return reformated

        else:
            for max_depth in reversed(range(actual_max_depth)):
                reformated = Formatter.reformat_text(
                    text, blocks, token_list, token_string, depths, token_chars,
                    token_patterns, indent_str, default_token_char, max_depth
                )
                if len(reformated) > len(text):
                    continue

                if text == reformated:
                    reformated = Formatter.reformat_text(
                        text, blocks, token_list, token_string, depths, token_chars,
                        token_patterns, indent_str, default_token_char, max_depth-1
                    )
                    if text == reformated: break
                    return reformated
                if len(reformated) < len(text):
                    # it will only get shorter
                    reformated = Formatter.reformat_text(
                        text, blocks, token_list, token_string, depths, token_chars,
                        token_patterns, indent_str, default_token_char, max_depth
                    )
                    if text == reformated: break
                    return reformated


        return Formatter.reformat_text(
            text, blocks, token_list, token_string, depths, token_chars,
            token_patterns, indent_str, default_token_char, 0
        ) 



    @staticmethod
    def build_token_list(text, token_patterns, default_token):
        
        token_list = []

        last_token_end = 0
        for i in range(len(text)):
            for k,token_pattern in enumerate(token_patterns):
                if text[i:i+len(token_pattern)] == token_pattern:
                    if last_token_end < i:
                        token_list.append(Token(default_token,last_token_end,i,""))

                    token_list.append(Token(k,i,i+len(token_pattern),""))
                    last_token_end = i+len(token_pattern)
        if last_token_end < len(text):
            token_list.append(Token(default_token,last_token_end,len(text),""))
        return token_list

    @staticmethod
    def build_token_string(token_list, token_chars, default_token_char):
        return "".join(
            map(
                (lambda token: (token_chars[token.token_type] if token.token_type >= 0 else default_token_char))
                , token_list
            )
        )

    @staticmethod
    def strip_tokens(text, token_list, strip_chars="\r\n\t "):
        result_list = []
        for i in range(len(token_list)):
            token = token_list[i]

            len_lstripped = len(text[token.start:token.end].lstrip(strip_chars))
            num_strip_l = token.length() - len_lstripped
            len_rstripped = len(text[token.start+num_strip_l:token.end].rstrip(strip_chars))
            num_strip_r = len_lstripped - len_rstripped
            start, end = token.start + num_strip_l, token.end - num_strip_r
            if end > start:
                result_list.append (
                    Token (
                        token.token_type, 
                        start, 
                        end, 
                        token.string.strip(strip_chars)
                    )
                )

        return result_list


    @staticmethod
    def match_tokens_with_token_string(text, token_list, token_string, token_chars, token_strings, default_token_char):
        # build new token list:
        # if token is in token_chars use direct string token
        # if token is indirect, take next indirect from token_list
        token_list_indirects = iter(filter((lambda token: (token.token_type < 0)), token_list))

        result_list = []
        for i in range(len(token_string)):
            if token_string[i] == default_token_char:
                token_list_indirect = next(token_list_indirects)
                result_list.append(Token(-1, 0, 0, text[token_list_indirect.start:token_list_indirect.end]))
            else:
                for k in range(len(token_chars)):
                    if token_string[i] == token_chars[k]:
                        result_list.append(Token(k, 0, 0, token_strings[k]))
                        break
        return result_list

    @staticmethod
    def text_from_token_list(text, token_list):
        result = []
        for i in range(len(token_list)):
            result.append(token_list[i].as_text(text))

        return "".join(result)

    @staticmethod
    def fold_all(text, token_list):
        return Formatter.strip_tokens(text, token_list)

    @staticmethod
    def build_blocks(token_string, open_tokens = ["<","(","{","["], close_tokens = [">",")","}","]"], separator_tokens=[","]):
        blocks = [Block(0,None,None,None,0,len(token_string)-1)]
        stack = [0]
        for i in range(len(token_string)):
            current_block = stack[len(stack)-1]
            if token_string[i] in open_tokens:
                new_id = len(blocks)
                new_block = Block(new_id, token_string[i], None, blocks[current_block], i)
                blocks[current_block].children.append(new_id)
                blocks.append(new_block)
                stack.append(new_id)
            elif token_string[i] in close_tokens:
                blocks[current_block].close_token = token_string[i]
                blocks[current_block].end = i
                stack.pop()
            elif token_string[i] in separator_tokens:
                blocks[current_block].separators.append(i)

        for i in range(len(blocks)):
            if blocks[i].end is None:
                blocks[i].end = len(token_string)
        
        return blocks

    @staticmethod
    def build_depths(blocks, num_tokens):
        depths = [0] * num_tokens
        for i in range(1,len(blocks)):
            block = blocks[i]
            for k in range(block.start+1, block.end):
                depths[k] = max(depths[k], block.depth)
        return depths

    @staticmethod
    def insert_new_lines(blocks, token_string, depths, max_depth, new_line_token=" ", indent_token = "_"):
        insert_before = [False] * len(token_string)
        insert_after = [False] * len(token_string)
        for i in range(1,len(blocks)):
            block = blocks[i]
            if max_depth >= 0 and block.depth > max_depth: continue
            if block.content_length() < params.min_content_length: continue
            if (len(block.children) == 0) and len(block.separators) < params.min_seperators: continue
            # if len(block.children) == 0: continue
            insert_before[block.start] = True
            insert_after[block.start] = True
            insert_before[block.end] = True
            insert_after[block.end] = True
            for k in range(len(block.separators)):
                insert_after[block.separators[k]] = True

        # return "\n".join(map(str,zip(depths,token_string,insert_after,insert_before)))

        result = []
        indented = False
        for i in range(len(token_string)):


            if not indented:
                result.append(indent_token * depths[i])
                indented = True

            result.append(token_string[i]) 

            if insert_after[i]:
                result.append(new_line_token)
                indented = False

            if (i+1<len(token_string)) and insert_before[i+1]:
            # if insert_before[i]:
                result.append(new_line_token)
                indented = False
        return "".join(result)

    @staticmethod
    def reformat_text(
            text, blocks, token_list, token_string, depths, token_chars,
            token_patterns, indent_str, default_token_char, max_depth):
        token_string2 = Formatter.insert_new_lines(blocks, token_string, depths, max_depth)
        token_list2 = Formatter.match_tokens_with_token_string(text, token_list, token_string2, token_chars+["_"], token_patterns+[indent_str], default_token_char)
        return Formatter.text_from_token_list(text,token_list2)

 

    @staticmethod
    def get_selection_from_region(
        region: sublime.Region, regions_length: int, view: sublime.View
    ) -> sublime.Region:
        selected_entire_file = False
        if region.empty() and regions_length > 1:
            return None, None
        elif region.empty() and s.get("use_entire_file_if_no_selection", True):
            selection = sublime.Region(0, view.size())
            selected_entire_file = True
        else:
            selection = region
        return selection, selected_entire_file
