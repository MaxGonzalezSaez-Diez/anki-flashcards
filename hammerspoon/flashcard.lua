-- Hammerspoon init.lua
-- Leader: cmd + shift + space, then:
-- f: flashcards (general)
-- p: paper flashcards (title, authors, main takeaways)
-- q: 2 questions on most recently discussed concepts
-- l: latex
-- e: explain
-- c: clean up text
-- s: summarize
-- r: random knowledge tidbit

------------------------------------------------------------
-- Helper: clipboard + paste workflow
------------------------------------------------------------

local function runWithInjectedText(text)
    local old = hs.pasteboard.getContents()

    hs.pasteboard.setContents(text)
    hs.eventtap.keyStroke({"cmd"}, "v")

    hs.timer.doAfter(0.02, function()
        hs.eventtap.keyStroke({}, "return")
    end)

    hs.timer.doAfter(0.1, function()
        hs.pasteboard.setContents(old)
    end)
end

------------------------------------------------------------
-- Modal leader setup
------------------------------------------------------------
local leader = hs.hotkey.modal.new({"cmd", "shift"}, "space")

local exitTimer = nil

local function armTimeout()
    if exitTimer then exitTimer:stop() end
    exitTimer = hs.timer.doAfter(2, function()
        leader:exit()
    end)
end

leader:entered(function()
    armTimeout()
end)

leader:exited(function()
    if exitTimer then exitTimer:stop() end
    exitTimer = nil
end)

------------------------------------------------------------
-- Shared base prompt for all QQQ/AAA flashcard shortcuts
------------------------------------------------------------

local BASE_QA_PROMPT = [[
You are a flashcard generator. Read the FULL conversation and produce flashcards covering the key ideas worth long-term retention. Ignore operational/task chatter.

GENERAL INSTRUCTIONS:

RULES:
- Focus on the MOST important concepts, intuitions, derivations, definitions, and reusable reasoning patterns.
- Every question must be FULLY self-contained.
- Do NOT generate duplicate or near-duplicate questions.
- Render equations in LaTeX and code in fenced markdown.

FLASHCARD TYPES:
1. Recall Flashcards
    - For definitions, summaries, terminology, and paper metadata.
    - Keep answers EXTREMELY concise (typically 1–2 bullets).

2. Reconstruction Flashcards
    - For math, algorithms, proofs, ML, physics, statistics, or any concept requiring multi-step reasoning.
    - These answers MUST be reconstructable from first principles.
    - Assume the reader has forgotten most of the topic and only remembers basic prerequisites.
    - Do NOT use expert shorthand or skip reasoning steps.
    - Explicitly explain:
        - where equations come from,
        - what substitutions/manipulations are being made,
        - why each step is valid,
        - what symbols mean,
        - and the intuition behind the result.
    - Reconstruction flashcards may be long if needed for clarity, NEVER skip logical steps
    - Include ALL intermediate algebra steps.
    - Define variables before using them.
    - Explain why operations are allowed.
    - When introducing a formula, explain its origin.
    - If a derivation depends on an unstated theorem or identity, briefly state it.
    - Explain steps it explicitly so that in 2 years someone can follow the logic.

STRICT FORMAT — do not deviate:

QQQ: [fully self-contained question]
AAA:
    - [answer bullet or derivation step]
    - [answer bullet or derivation step]

]]

------------------------------------------------------------
-- "f" — general flashcards
------------------------------------------------------------
leader:bind("", "f", function()
    leader:exit()
    runWithInjectedText(BASE_QA_PROMPT .. [[
]])
end)

------------------------------------------------------------
-- "p" — paper-only flashcards
------------------------------------------------------------
leader:bind("", "p", function()
    leader:exit()
    runWithInjectedText(BASE_QA_PROMPT .. [[
SPECIFIC INSTRUCTIONS - You are now only generating flashcards for a paper (Recall Flashcards):
- Focus ONLY on the most recently discussed paper.
- Generate MAXIMUM 1 flashcards total covering:
  Title, authors (FIRST et al. (Last Author, University/Lab)), and publication venue + main message / core contribution / takeaways (can be multiple bullet points. Make sure to list all the key takeaways from the paper) + One bullet point for anything important to remember. I do NOT want equations or nigtty-gritty details but overall things I should remember.
- Do NOT cover topics outside this paper. 
- STAY EXTREMELY CONCISE AND TO THE POINT. I do not want to memorize long lists of bullet points but rather a few SHORT, KEY concepts and ideas.

Author flashcard example:
QQQ: What is the title, authorship, publication venue, and main contributions of the paper investigating [1-sentence summary]?
AAA:
    - Title: [paper title]
    - Authors: FIRST et al. (Last Author, University/Lab)
    - Venue: [journal/conference] ([year])
    - Contributions: 
        - [key contribution 1]
        - [key contribution 2]
        - [key contribution 3]
]])
end)



------------------------------------------------------------
-- "q" — 2 quick questions on most recent concepts
------------------------------------------------------------
leader:bind("", "q", function()
    leader:exit()
    runWithInjectedText(BASE_QA_PROMPT .. [[
ADDITIONAL INSTRUCTIONS:
- Read the full conversation and generate flashcards on the topics discussed that DO NOT ALREADY HAVE A FLASHCARD.
- Do NOT generate duplicate or near-duplicate questions.
- Do Not generate flashcards on papers.
- STAY EXTREMELY CONCISE AND TO THE POINT. I do not want to memorize long lists of bullet points but rather a few SHORT, KEY concepts and ideas.
- Make sure to only focus on important ideas that I should remember.
- Generate FEW flashcards only on the most important ideas, it's not helpful to generate many to ensure extensive coverage as it wont be possible to memorize all of them. Instead pick the most relevant/ideas and generate a few flashcards on them.
]])
end)

------------------------------------------------------------
-- "l" — LaTeX
------------------------------------------------------------
leader:bind("", "l", function()
    leader:exit()
    runWithInjectedText([[Please execute the request and add a separated block of LaTeX that is directly copy-pasteable into overleaf]])
end)

------------------------------------------------------------
-- "e" — explain
------------------------------------------------------------
leader:bind("", "e", function()
    leader:exit()
    runWithInjectedText([[I am confused by the concepts. Please explain the concepts in a simple, clear way. Avoid overly technical language unless it is necessary. If technical terms are used, briefly define them in simple words. When explaining, use step-by-step reasoning and do not skip intermediate steps, even if they seem obvious. Walk through the full reasoning process in a logical order. If possible, include a simple or medium difficulty example. When giving an example, go through it step by step so the process is fully visible and easy to follow.]])
end)

------------------------------------------------------------
-- "c" — clean up text
------------------------------------------------------------
leader:bind("", "c", function()
    leader:exit()
    runWithInjectedText([[I have provided you with a text snippet. Read the complete text carefully and produce a revised version that corrects any grammatical errors, typos, and unclear constructions. Rewrite the text to improve clarity and precision while preserving the original meaning, tone, and style as closely as possible. Avoid vague, abstract, or inflated language, and prefer concrete, specific wording wherever possible. Replace unnecessary long or pretentious words with simpler, more direct alternatives unless the original style clearly requires them. Eliminate redundant words, filler phrases, and ready-made expressions that do not add meaning, and prefer the active voice over the passive where it improves clarity. Do not introduce new ideas, remove content, or alter the intended message in any way, and ensure that each sentence expresses a clear and definite meaning while remaining faithful to the original structure and intent. Do NOT use ';' or em-dashes.]])
end)

------------------------------------------------------------
-- "s" — summarize
------------------------------------------------------------
leader:bind("", "s", function()
    leader:exit()
    runWithInjectedText([[I have provided you a long text (paper, article, etc.). Please summarize the text. Focus on the most important insights. Structure the response as: 1. provide the core intuition for what's going on 2a. walk me through the key points and takeaways of the text 2b. walk me through the key equations (if any relevant ones exist). For both 2a/2b, please walk me through numerical examples where appropriate. 3. Describe any limitations of the text, such as assumptions that are made, or areas where the text could be improved. 

    Always provide direct quotes from the text to support your points (so I can verify the information. Always render equations in Latex.)]])
end)

------------------------------------------------------------
-- "r" — random knowledge tidbit
------------------------------------------------------------
leader:bind("", "r", function()
    leader:exit()
    runWithInjectedText([[Please generate a random history, economics, politics, philosophy or religious knowledge tidbit that is interesting. You can also generate an interesting quote from a famous person in any of those fields. Please formulate the tidbit in the form of a question and answer flashcard, where the question is fully self-contained and can be understood without any prior context. The answer should be a few bullet points that explain the concept in a clear and concise way.
    QQQ: [fully self-contained question/prompt]
    AAA:
        - [here knowledge tidbit or quote, written as a full sentence or short explanatory paragraph]
    ]])
end)


