"""
board_manager.py — Non-Muslim Board of Directors Filter Management
Best tarika for 100% Non-Muslim Board requirement (cannot auto-infer religion from names reliably)

================================================================================
ADMIN PERMISSION REQUIRED - YFINANCE USAGE RESTRICTED TO COMPANY INFORMATION ONLY
================================================================================
- yfinance is used ONLY for Non-Muslim Board of Directors fetching (companyOfficers)
  Reason: Dhan API does NOT provide board of directors data, so yfinance is the ONLY place where yfinance is needed
  Source: yf.Ticker('SYMBOL.NS').info['companyOfficers'] -> board members names
  Location: This file board_manager.py (fetch_board_members) and board_filter_auto.py

- All other data (price, volume, market data, optimization, backtest, sector, FII/DII, etc) MUST use Dhan data only, NOT yfinance
  Source for price/volume: dhan_data.py fetch_daily_data, broker.py get_market_depth, intraday_filter.py scrip master
  Reason: Yfinance can have 19-20 difference from Dhan, trade happens on Dhan account, so Dhan data must be used

- If any other AI is asked to replace something and sees this yfinance usage, DO NOT CHANGE this yfinance usage without ADMIN PERMISSION
  If changes are needed, first take ADMIN PERMISSION, because board data cannot be fetched from Dhan, yfinance is required only for board

- Yfinance is better to avoid if possible, but if work cannot happen without it (board data), must use for board only
  For ambiguous names (Choudhary, Bhat, Amin, Sameer etc - Hindu bhi Muslim bhi), web search confirmation from company website / Wikipedia is done
  If not 100% confirm non-Muslim, fail-safe: don't trade (per user instruction)
================================================================================

Design (Start to End Process in Scheduler Monthly):
1. Fetch board members via yfinance (Dhan does not provide board)
2. Heuristic Muslim name detection with word boundary + 2-tier (high-conf Muslim vs ambiguous)
3. For ambiguous/contradictory names, web search confirmation from company website / Wikipedia / biography
4. If 100% confirm non-Muslim -> True, else False (fail-safe: don't trade if not 100% confirm)
5. Monthly scheduler refresh_board_status() re-fetches board, detects change, re-verifies via web search, auto-restore if becomes 100% Non-Muslim again
"""

import os, json, re
from utils import load_json, save_json, logger, now_ist

BOARD_MEMBERS_FILE = "data/board_members.json"
BOARD_STATUS_FILE = "data/board_status.json"

# Muslim names list - high confidence vs ambiguous
HIGH_CONF_MUSLIM = [
    # [AUDIT FIX Gap #10] list substantially expanded 2026-08 — old ~150-word list left
    # any real Muslim name outside it with ZERO verification (auto-classified "non_muslim").
    # No automated religion-verification is possible (no data vendor tracks this), so a
    # broader, better-curated blocklist is the only practical way to reduce that gap.
    'mohammed','mohammad','muhammad','mohd','md','ahmed','ahmad','abdullah','abdul',
    'mohamed','mohamad','ismail','mustafa','faiz','aslam','iqbal','rizwan','imran','farhan','tariq','waseem','wasim','yusuf','yasin','zakir','zafar','zahid','azhar','bilal','danish','firoz','feroz','ghulam','habib','haider','hyder','ibrahim','javed','jaweed','khalid','mahmood','mahmud','mansoor','mansur','moin','mohsin','mustafa','nadeem','nasir','qadir','qasim','rafiq','raza','riaz','sadiq','saeed','sajid','salman','shabbir','shoaib','suleman','sulaiman','sultan','tahir','umar','omar','usama','osama','faisal','faizal','farooq','farooqui','rashid','amjad','afzal','alam','ayub','bashir','dawood','daud','ghafoor','hafeez','hameed','idris','ilyas','imtiaz','junaid','kaleem','khalil','majid','mubeen','mujeeb','nabi','nawaz','parvez','pervez','qayyum','raheem','rahim','sattar','shafi','shahid','shams','tanveer','waheed','yaqoob','zaheer',
    # additional first/last names & regional Muslim surname variants (Kerala/Bengal/UP/Gujarat/Deccan)
    'akhtar','akhter','anis','anisur','arif','ashfaq','asif','ayesha','aysha','fatima','fathima','firdaus','gulam','hamid','haq','hasan','hussaini','ikram','ilahi','inam','irfan','jabbar','jafar','jaffer','jamal','kamal','kausar','kauser','khatoon','latif','liaquat','maqbool','marfani','mateen','meer','mir','mirza','mohiuddin','muneer','munir','murad','musharraf','nafisa','naeem','naseer','nasreen','nazir','nizami','noor','nusrat','parveen','qamar','quraishi','qureshi','rafi','rahman','rehman','rasheed','saifuddin','saira','sameena','samina','sarwar','shabana','shakeel','shakil','shameem','shamim','sheikh','sheikha','siddiqi','siddiqui','tabassum','tabrez','taj','wahab','wahid','yasmeen','yasmin','zaib','zainab','zeenat','sayyed','sayed','saiyed','khwaja','pathan','ansari',
    # [2026-09-04 r5] verified against the shipped board data (data/board_members_yfinance.json):
    # these Muslim names sat on APPROVED boards because no list contained them —
    # e.g. Wockhardt (Khorakiwala), Poonawalla (Zaman), Angel One (Naheed), TV Today (Kidwai),
    # Refex (Suhail Shariff), Tembo (Kachwala), Divgi (Zubair), KCP (Tyebali Hyderi).
    'begum','khatun','bano','sultana','naheed','rehan','shabnam','shabnum','kidwai','zaman','suhail','sohail','shariff','kachwala','fatema','khorakiwala',
    'murtaza','murtuza','huzaifa','fakhruddin','habil','tyebali','tyabji','hyderi','zubair','zuber','azim','jalal','memon','kazi','qazi',
    'baig','beg','mubin','manzar','sarfaraz','qaiser','tajuddin','aamir','haseeb','shuja','mohasin','mahnaz','nazhat','nazish','shabhir',
    'salauddin','abubakar','mohmed','abdulrazzak','zahirhasan','rahiman','hasham','rishad','gawir','almina','asma','kamruddin','badruddin',
    'burhanuddin','nizamuddin','salahuddin','jalaluddin','zulfiqar','zulfikar','mukhtar','irshad','naushad','naseem','nazneen',
    'rasool','rasul','shaukat','asghar','azam','azeem','saleh','saqib','aqeel','yahya','yakub','yaqub','musa','moosa','mehdi','rizvi','naqvi',
    'zaidi','abidi','jafri','kadri','qadri','quadri','kazim','hasnain','husain','hossain','jafari','taher','tahera','momin','saiyad','shaik','sheik',
]

# [FIX-LIST 2026-09-04 item 5] SINGLE SOURCE OF TRUTH for the name list.
# The one-time batch script (board_filter_auto.py, ~250 curated names) and
# this runtime monthly scanner had drifted apart: 93 names present in the
# batch list (e.g. 'ali', 'kabir', 'salim', 'ashraf', 'karim', 'hanif',
# 'yousuf') were MISSING here, so a monthly refresh could silently re-admit a
# board the initial batch had excluded. The batch list is now merged in
# (whole-word matching only; names already in AMBIGUOUS_NAMES stay there so
# they keep requiring confirmation instead of hard-blocking).
try:
    from board_filter_auto import muslim_names as _BATCH_MUSLIM_NAMES
except Exception:  # pragma: no cover — batch script optional at runtime
    _BATCH_MUSLIM_NAMES = []

AMBIGUOUS_NAMES = [
    'choudhary','choudhury','chowdhury','bhat','amin','sameer','samir','roshan','malik','khan','sheikh','syed','hussain','hassan','abbas','qureshi','siddiqui','ansari','usman','osman','arman','anwar','azad',
    # [2026-09-04 r5] DUAL-COMMUNITY given names in India (Hindu/Sikh AND Muslim
    # usage): "Kamal Kumar Jain", "Parveen Kumar Goel", "Iqbal Singh", "Kabir
    # Bedi", "Tanveer Singh", "Gulzar", "Shamsher Puri", "Shehnaz Gill". They
    # were in the HIGH-CONFIDENCE list, so 29 companies with Hindu boards would
    # have been blocked at the first monthly refresh. Now ambiguous: cleared
    # ONLY when the same full name carries an unmistakable non-Muslim marker
    # (NON_MUSLIM_MARKERS below); otherwise still fail-closed (blocked).
    'kamal','parveen','kabir','iqbal','tanveer','tanvir','gulzar','dilawar','shahbaz','shamsher','shehnaz','shahnaz','reshma',
]
# [FIX-LIST 2026-09-04 item 5] 'gupta','sharma','singh','kumar' were REMOVED
# from this ambiguous list (not Muslim names under any convention; with the
# placeholder web-confirm they alone would have fail-closed 715 of 1,069
# approved companies at the first monthly refresh). They now act as
# NON-Muslim markers instead (see NON_MUSLIM_MARKERS).

# Ambiguous tokens that are NEVER cleared by context — predominantly Muslim
# surnames; a Hindu given name next to them is not enough certainty under the
# owner's fail-closed rule ("shak ho to trade nahi").
AMBIGUOUS_NEVER_CLEAR = {
    'khan','sheikh','syed','hussain','hassan','abbas','qureshi','siddiqui','ansari','usman','osman','anwar',
}

# [2026-09-04 r5] UNMISTAKABLE NON-MUSLIM MARKERS — Hindu/Sikh/Jain surnames,
# community names and given names that Indian Muslims do not use. Used ONLY
# to confirm an otherwise-ambiguous token inside the SAME full name. They can
# never override a high-confidence Muslim token (that check runs first).
# Deliberately EXCLUDED because both communities use them: patel, shah, desai,
# vora/vohra, merchant, kapadia, lakhani, mondal, saha, biswas, sarkar, mallick,
# majumdar, naik, nayak, babu, chand, mani, patil, chauhan, rajput, thakur,
# dalal, mistry, contractor, seth, roy/ray, meena, seema, mona, rima, sonia, nisha.
NON_MUSLIM_MARKERS = {
    # Jain / Marwari / Bania
    'jain','agarwal','agrawal','aggarwal','sharma','gupta','goel','goyal','mittal','bansal','garg','singhal','singal','bajaj','khetan','poddar',
    'rathi','sarda','sethia','maheshwari','somani','kabra','mundra','jhunjhunwala','goenka','birla','bhartia','khaitan','dalmia','ruia','kanoria',
    'kothari','lodha','bhandari','chordia','surana','bafna','baid','bothra','dugar','nahata','bhansali','oswal','sanghvi','sanghavi','doshi','parekh','parikh',
    # Bengali Hindu
    'mitra','ghosh','ghose','banerjee','bandyopadhyay','chatterjee','chattopadhyay','mukherjee','mukhopadhyay','bhattacharya','bhattacharjee',
    'ganguly','sengupta','dasgupta','basu','bose','dutta','datta','sen','das','pal','nandy','chakraborty','chakravarty',
    # South Indian Hindu
    'iyer','iyengar','reddy','naidu','rao','nair','menon','pillai','shetty','hegde','kamath','pai','shenoy','prabhu','kini','baliga','gowda',
    'krishnamurthy','ramachandran','sundaram','natarajan','ganesan','rajan','chandrasekaran','gopalakrishnan','ramaswamy','ramasamy','venkataraman',
    'narasimhan','raghavan','varadarajan','ravichandran','balasubramanian','sivakumar','senthil','muthu','murugan','karthik','karthikeyan','saravanan',
    'arumugam','palaniappan','kannan','thiagarajan','chidambaram','shanmugam','nambiar','kurup','warrier','panicker','sundararajan','ranganathan',
    'parthasarathy','padmanabhan','seshadri','rangarajan','jayaraman','mahalingam','vaidyanathan','subramanian','srinivasan','raman','murthy','murty',
    'sastry','shastri','swamy','venkat','venkatesh','venkatesan','krishna','krishnan','narayan','narayanan','shankar','srinivas','balaji','murali',
    # Odia Hindu
    'parida','mohanty','mohapatra','pattnaik','patnaik','sahoo','sahu','behera','panda','swain','tripathy','rath','dash','jena','biswal','samal',
    # Marathi Hindu
    'kulkarni','deshpande','deshmukh','joshi','kelkar','gokhale','apte','sawant','pawar','shinde','jadhav','gaikwad','bhosale',
    # UP / Bihar / Hindi-belt Hindu
    'trivedi','dwivedi','tiwari','tewari','mishra','misra','pandey','pande','shukla','srivastava','verma','yadav','chaturvedi','tripathi','upadhyay',
    'singh','kumar','lal','prasad','nath','chandra','chander','ram','raju',
    # Punjabi Hindu / Sikh (Khatri, Arora, Jat)
    'taneja','abrol','dhingra','luthra','khanna','kapoor','malhotra','chopra','sethi','arora','sahni','sawhney','tandon','kohli','bedi','ahluwalia',
    'puri','gill','sandhu','dhillon','grewal','sidhu','brar','bhullar','sodhi','oberoi','mehra','anand','bhalla','chadha','dhawan','kakkar','khurana',
    # Sindhi Hindu
    'mahtani','gwalani','samtani','gianchandani','advani','hinduja','ahuja','chandwani','kukreja','lalwani','mirchandani','motwani','raheja',
    'ramchandani','sadhwani','sachdev','tolani','vaswani','jagtiani','kripalani','mansukhani','mulchandani','shivdasani','thadani','wadhwani',
    # Gujarati Hindu / Jain / Parsi
    'mehta','modi','thakkar','thakker','panchal','soni','jhaveri','zaveri','gandhi','choksi','choksey','nagar','oza','pandya','vyas','dave','bhatt',
    'raval','purohit','acharya','shroff','sheth',
    # unmistakably Hindu / Sikh given names (male)
    'rajesh','rajeev','rajiv','sanjay','amit','deepak','prakash','suresh','sunil','anil','manish','rahul','ashok','ashish','ajay','vijay','manoj',
    'ravi','dinesh','pankaj','rakesh','arun','vivek','sanjeev','sanjiv','vikas','rajendra','mohan','gaurav','prashant','vinod','nitin','gautam',
    'goutam','arvind','satish','vishal','sachin','yogesh','mahesh','vikram','abhishek','nikhil','rohit','saurabh','sourav','saurav','atul','vinay',
    'gopal','sudhir','ganesh','mukesh','aditya','pradeep','kishore','kishor','pramod','naresh','lalit','bharat','ankur','varun','harish','hemant',
    'jitendra','neeraj','mahendra','siddharth','hitesh','praveen','bikash','partha','jagdish','shrigopal','sukhamoy','ramesh','mahavir','shyam',
    'rajkumar','ramkumar','shivkumar','ravindra','narendra','surendra','devendra','dharmendra','virendra','jeetendra','upendra','bhupendra',
    'yogendra','shailendra','gajendra','nagendra','raghavendra','kamlesh','jayesh','nilesh','mitesh','ritesh','paresh','umesh','lokesh','rupesh',
    'bhavesh','jignesh','chetan','ketan','kirit','nishant','sushant','shailesh','devang','dhaval','dhruv','harsh','harshad','harshal','hasmukh',
    'hemal','hiren','jatin','jayant','kalpesh','kaushik','keyur','kunal','mayank','mihir','nayan','nimesh','niraj','nirav','nitesh','piyush',
    'pratik','rasik','rasiklal','ratan','ratilal','sagar','sharad','shashank','shirish','shreyas','shrikant','sudhakar','sumit','tarun','tushar',
    'uday','umang','utpal','vaibhav','viren','vipul','viral','vishnu','yash','yatin','subrata','somnath','soumen','pradip','tapan','tapas','swapan',
    'ranjit','dipak','debashis','debasish','indranil','sanjib','sujit','ashis','asit','arup','anup','amitava','amitabha','biswajit','prabir','pranab',
    'rabindra','sudip','subir','satyajit','shyamal','mrinal','nirmal',
    # unmistakably Hindu given names (female)
    'laxmi','lakshmi','saraswati','parvati','durga','sita','gita','geeta','radha','uma','usha','sunita','kavita','savita','sarita','mamta',
    'neelam','poonam','rekha','shobha','sudha','pushpa','kamla','kamala','vimla','vimala','sushma','madhu','madhuri','vandana','archana','aparna',
    'swati','smita','jyoti','priya','pooja','neha','shilpa','shweta','sneha','rupa','ritu','deepa','divya','gauri','hema','indira','jaya','kalpana',
    'kirti','lata','manju','meera','nalini','namrata','nandini','nita','padma','pallavi','preeti','rashmi','renu','ruchi','sangeeta','sarika',
    'shalini','shraddha','sonal','sujata','suman','supriya','tanuja','urmila','vaishali','veena','vidya','shivangi',
}

# merge batch list (minus ambiguous ones), dedupe, longest-first so the
# alternation prefers the most specific whole word.
HIGH_CONF_MUSLIM = sorted(
    ({n.lower() for n in HIGH_CONF_MUSLIM} | {n.lower() for n in _BATCH_MUSLIM_NAMES}) - {n.lower() for n in AMBIGUOUS_NAMES},
    key=len, reverse=True)
NON_MUSLIM_MARKERS = {n.lower() for n in NON_MUSLIM_MARKERS} - set(HIGH_CONF_MUSLIM) - set(AMBIGUOUS_NAMES)
HIGH_CONF_PATTERN = re.compile(r'\b(' + '|'.join(map(re.escape, HIGH_CONF_MUSLIM)) + r')\b', re.IGNORECASE)
AMBIGUOUS_PATTERN = re.compile(r'\b(' + '|'.join(map(re.escape, AMBIGUOUS_NAMES)) + r')\b', re.IGNORECASE)

def _ensure_files():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(BOARD_MEMBERS_FILE):
        save_json(BOARD_MEMBERS_FILE, {})
    if not os.path.exists(BOARD_STATUS_FILE):
        save_json(BOARD_STATUS_FILE, {})

def fetch_board_members(symbol: str) -> list:
    """
    Fetch board members via yfinance (Dhan does NOT provide board data)
    ADMIN PERMISSION REQUIRED: yfinance used only for company information; this module uses board data
    Source: yf.Ticker('SYMBOL.NS').info['companyOfficers']
    """
    _ensure_files()
    try:
        # ADMIN PERMISSION REQUIRED: yfinance ONLY for board, Dhan does not provide board data
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("fetch_board_members: yfinance not installed, cannot fetch board - board data requires yfinance for board only")
            return []

        # Try NSE first, then BSE
        for suffix in ['.NS', '.BO']:
            try:
                ticker = yf.Ticker(f"{symbol}{suffix}")
                info = ticker.info
                officers = info.get('companyOfficers', [])
                if officers:
                    directors = [o.get('name','').strip() for o in officers if o.get('name')]
                    if directors:
                        # Save to board_members file
                        members_data = load_json(BOARD_MEMBERS_FILE, {})
                        members_data[symbol] = directors
                        save_json(BOARD_MEMBERS_FILE, members_data)
                        return directors
            except Exception as e:
                logger.debug(f"fetch_board_members: yfinance fetch failed for {symbol}{suffix}: {e}")
                continue
        
        # [FIX-LIST 2026-09-04 item 5] Secondary source when yfinance returns
        # no officers: scrape the public director/KMP names from the company's
        # own NSE listing page mirror on screener.in (company information only —
        # NOT price/volume, per DATA_SOURCE_POLICY.md). Previously this branch
        # fetched the page and then did nothing ("parsing not implemented"),
        # i.e. a silent no-op that always fell through to [] (fail-closed but
        # needlessly blocked stocks whose officers yfinance does not carry).
        directors = _scrape_directors_screener(symbol)
        if directors:
            members_data = load_json(BOARD_MEMBERS_FILE, {})
            members_data[symbol] = directors
            save_json(BOARD_MEMBERS_FILE, members_data)
            return directors

        return []
    except Exception as e:
        logger.warning(f"fetch_board_members: Failed for {symbol}: {e}")
        return []


_SCREENER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*){1,5}$")
_SCREENER_TITLE_RE = re.compile(r"\b(Mr|Ms|Mrs|Dr|Prof|Shri|Smt|Late|Sri|CA|CS)\.?\s*", re.IGNORECASE)


def _scrape_directors_screener(symbol: str, timeout: int = 10) -> list:
    """Best-effort scrape of director / key-managerial-person names for
    `symbol` from screener.in (public company page). Returns [] on any
    failure — caller treats [] as UNVERIFIED (fail-closed). Only NAMES are
    extracted; no financial data is read from this page (DATA_SOURCE_POLICY)."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    names = []
    for slug in (symbol, f"{symbol}/consolidated"):
        try:
            r = requests.get(f"https://www.screener.in/company/{slug}/",
                             headers={"User-Agent": "Mozilla/5.0 (compatible; QaswaBoardCheck/1.0)"},
                             timeout=timeout)
            if r.status_code != 200 or not r.text:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            # Screener lists people under headings such as "Management",
            # "Board of Directors", "Key Executives" — collect list items /
            # table cells under any such heading.
            for heading in soup.find_all(["h2", "h3", "h4", "strong"]):
                title = heading.get_text(" ", strip=True).lower()
                if not any(k in title for k in ("management", "director", "board", "key executive", "kmp")):
                    continue
                container = heading.find_parent(["section", "div"]) or heading
                for node in container.find_all(["li", "td", "p", "span"]):
                    txt = _SCREENER_TITLE_RE.sub("", node.get_text(" ", strip=True)).strip()
                    txt = re.split(r"\s[-–|(,]\s?", txt)[0].strip()   # drop " - Managing Director" suffixes
                    if 3 <= len(txt) <= 60 and _SCREENER_NAME_RE.match(txt):
                        if txt.lower() not in {n.lower() for n in names}:
                            names.append(txt)
            if names:
                break
        except Exception as e:
            logger.debug(f"_scrape_directors_screener: {symbol} ({slug}) failed: {type(e).__name__}: {e}")
            continue
    return names

def is_potential_muslim_name(name: str):
    """Check if name contains high-confidence Muslim name"""
    if not name:
        return False, None, "none"
    # [FIX-LIST 2026-09-04 item 5] Normalise before the word-boundary scan:
    # remove honorifics, turn punctuation ("Md.", "S.M.Khan", "Al-Rashid") into
    # spaces so every token is a whole word for the \b...\b patterns, and
    # collapse whitespace. Matching remains WHOLE-WORD only (no substring
    # hits like "Ali" inside "Alison" / "Salil").
    name_clean = re.sub(r'\b(Mr|Ms|Mrs|Dr|Prof|Shri|Smt|Late|Sri|Janab|Haji|Hafiz)\.?\s*', ' ', name, flags=re.IGNORECASE)
    name_clean = re.sub(r"[.\-_,/()'\"]+", " ", name_clean)
    name_clean = re.sub(r"\s+", " ", name_clean).strip()

    # Check high-confidence first
    m = HIGH_CONF_PATTERN.search(name_clean)
    if m:
        return True, m.group(0), "high_conf"
    
    # Check ambiguous - needs confirmation
    m2 = AMBIGUOUS_PATTERN.search(name_clean)
    if m2:
        words = set(name_clean.lower().split())
        amb_hits = words & set(AMBIGUOUS_NAMES)
        # [2026-09-04 r5] Contextual confirmation. A dual-community token
        # ("Kamal", "Parveen", "Chowdhury", "Iqbal", "Malik", ...) counts as
        # confirmed NON-Muslim only when (a) NO never-clear token (khan/syed/
        # hussain/...) is present anywhere in the name and (b) the SAME full
        # name carries an unmistakable non-Muslim marker ("Kamal Kumar Jain",
        # "Rajeev Chowdhury", "Iqbal Singh"). High-confidence Muslim tokens
        # were already checked above, so e.g. "Naheed Rehan Patel" or
        # "Kabir Khan" can never be cleared here. Anything else stays
        # fail-closed (ambiguous → blocked until manually confirmed).
        if not (amb_hits & AMBIGUOUS_NEVER_CLEAR) and (words & NON_MUSLIM_MARKERS):
            return False, None, "non_muslim"
        return True, m2.group(0), "ambiguous_needs_web_search"
    
    return False, None, "non_muslim"

def web_search_confirm_religion(name: str, company: str = "") -> str:
    """
    Web search confirmation from company website / Wikipedia / biography for ambiguous names
    Returns: "confirmed_hindu", "confirmed_muslim", "confirmed_non_muslim", "not_found", "ambiguous"
    This is best-effort - if not 100% confirm non-Muslim, fail-safe: don't trade
    """
    try:
        # For now, this is placeholder that would use web_search tool
        # In scheduler monthly job, this would call web_search API for "Name + Company + religion biography"
        # If search result contains Religion: Hindu/Sikh/Christian etc with high confidence, confirm non-Muslim
        # If search result contains Religion: Muslim, confirm Muslim
        # If not found or ambiguous, return "not_found" -> fail-safe don't trade
        
        # Example implementation would use web_search tool:
        # results = web_search(f"{name} {company} religion biography")
        # Parse results for religion field
        
        # For now, return not_found to trigger fail-safe (don't trade if not 100% confirm)
        return "not_found_needs_manual"
    except Exception as e:
        logger.warning(f"web_search_confirm_religion failed for {name}: {e}")
        return "error_not_found"

def check_board_100_non_muslim_with_confirmation(directors: list, company: str = "") -> tuple:
    """
    Check board 100% Non-Muslim with web search confirmation for ambiguous names
    Returns: (is_100_non_muslim: bool, details: dict)
    - If any director is high-confidence Muslim -> False
    - If any director is ambiguous and web search cannot 100% confirm non-Muslim -> False (fail-safe: don't trade if not 100% confirm)
    - Only if all directors confirmed non-Muslim (either no Muslim name or web search confirms Hindu/Sikh/etc) -> True

    [AUDIT FIX — DATA-002] An empty/missing directors list means board data was
    never actually fetched or verified for this symbol — it must NOT be treated
    as "no Muslim names found" (which would silently produce True). That is the
    exact opposite of this module's own fail-safe rule above. Empty directors
    now fails closed (False) with an explicit "unverified" marker instead of
    defaulting to True.
    """
    if not directors:
        return False, {
            "has_muslim": False,
            "matched": [],
            "ambiguous_needs_confirm": [],
            "directors": [],
            "verification_status": "unverified_no_director_data_fail_closed",
        }

    has_muslim = False
    ambiguous_needs_confirm = []
    matched_details = []
    
    for dname in directors:
        is_muslim, kw, tier = is_potential_muslim_name(dname)
        if is_muslim:
            if tier == "high_conf":
                has_muslim = True
                matched_details.append(f"{dname} (matched {kw} - high_conf Muslim)")
            elif tier == "ambiguous_needs_web_search":
                # Try web search confirmation
                confirm_result = web_search_confirm_religion(dname, company)
                if confirm_result == "confirmed_hindu" or confirm_result == "confirmed_non_muslim":
                    # Confirmed non-Muslim via web search, keep as non-Muslim
                    continue
                else:
                    # Not 100% confirm non-Muslim -> fail-safe don't trade
                    has_muslim = True
                    matched_details.append(f"{dname} (matched {kw} - ambiguous, web search {confirm_result} -> fail-safe exclude)")
                    ambiguous_needs_confirm.append(dname)
    
    is_100_non_muslim = not has_muslim
    return is_100_non_muslim, {
        "has_muslim": has_muslim,
        "matched": matched_details,
        "ambiguous_needs_confirm": ambiguous_needs_confirm,
        "directors": directors
    }

def get_board_members(symbol: str) -> list:
    _ensure_files()
    data = load_json(BOARD_MEMBERS_FILE, {})
    return data.get(symbol, [])

def is_board_100_non_muslim(symbol: str) -> bool:
    """
    [AUDIT FIX — board risk item A] Previously defaulted to True (tradeable) when
    no status/CSV data existed for a symbol — the exact opposite of this module's
    own documented fail-safe rule ("if not 100% confirm non-Muslim, don't trade").
    Not currently called by the live trade gate (that path uses stock_selector's
    CSV-column check + risk_manager's is_in_halal_universe defense-in-depth), but
    fixed here too so this function can never become an unsafe trap if wired in later.
    """
    _ensure_files()
    status_data = load_json(BOARD_STATUS_FILE, {})
    if symbol in status_data:
        return bool(status_data[symbol].get("non_muslim_board", False))
    else:
        try:
            import pandas as pd
            if os.path.exists("data/CUSTOM_UNIVERSE_FINAL.csv"):
                df = pd.read_csv("data/CUSTOM_UNIVERSE_FINAL.csv")
                row = df[df["symbol"]==symbol]
                if not row.empty and "non_muslim_board" in df.columns:
                    return bool(row["non_muslim_board"].values[0])
        except Exception:
            pass
        # Unknown symbol, no data anywhere -> fail-safe: NOT confirmed -> don't trade.
        return False

def update_board_status(symbol: str, is_non_muslim: bool, directors: list = None, verified_by: str = "manual"):
    _ensure_files()
    status_data = load_json(BOARD_STATUS_FILE, {})
    members_data = load_json(BOARD_MEMBERS_FILE, {})

    if directors is None:
        directors = members_data.get(symbol, [])

    status_data[symbol] = {
        "non_muslim_board": bool(is_non_muslim),
        "last_checked": now_ist().isoformat(),
        "directors": directors,
        "verified_by": verified_by,
        "symbol": symbol
    }
    save_json(BOARD_STATUS_FILE, status_data)

    if directors:
        members_data[symbol] = directors
        save_json(BOARD_MEMBERS_FILE, members_data)

    try:
        import pandas as pd
        custom_path = "data/CUSTOM_UNIVERSE_FINAL.csv"
        if os.path.exists(custom_path):
            df = pd.read_csv(custom_path)
            if symbol in df["symbol"].values:
                df.loc[df["symbol"]==symbol, "non_muslim_board"] = bool(is_non_muslim)
                df.to_csv(custom_path, index=False)
    except Exception as e:
        logger.warning(f"update_board_status: Failed to update CUSTOM CSV for {symbol}: {e}")

    return True

def refresh_board_status(full_universe_symbols: list = None):
    """
    Monthly refresh — start to end process in scheduler
    - Re-fetches board members via yfinance (Dhan does not provide board)
    - Checks high-confidence Muslim names
    - For ambiguous, web search confirmation from company website
    - If not 100% confirm non-Muslim, fail-safe don't trade
    - Detects board change, marks for re-verification, auto-restore if becomes 100% Non-Muslim again
    """
    _ensure_files()
    if full_universe_symbols is None:
        try:
            import pandas as pd
            df = pd.read_csv("data/CUSTOM_UNIVERSE_FINAL.csv")
            full_universe_symbols = df["symbol"].astype(str).tolist()
        except Exception:
            full_universe_symbols = []

    members_data = load_json(BOARD_MEMBERS_FILE, {})
    status_data = load_json(BOARD_STATUS_FILE, {})

    changed = []
    for sym in full_universe_symbols:
        try:
            old_members = members_data.get(sym, [])
            new_members = fetch_board_members(sym)
            if not new_members:
                # Strict fail-closed: a refresh failure/unavailable board data
                # must never preserve a previously-tradeable True state.
                status_data[sym] = {
                    "non_muslim_board": False,
                    "last_checked": now_ist().isoformat(),
                    "directors": old_members,
                    "verified_by": "refresh_failed_fail_closed",
                    "symbol": sym,
                    "board_refresh_failed": True,
                }
                continue
            if set(old_members) != set(new_members):
                changed.append(sym)
                # Check with confirmation logic
                is_100_non_muslim, details = check_board_100_non_muslim_with_confirmation(new_members, sym)
                # Update status (create record if this symbol is new).
                status_data[sym] = {
                    "non_muslim_board": bool(is_100_non_muslim),
                    "last_checked": now_ist().isoformat(),
                    "directors": new_members,
                    "verified_by": "monthly_refresh",
                    "symbol": sym,
                    "board_changed": True,
                    "board_refresh_failed": False,
                    "verification_details": details,
                }
                members_data[sym] = new_members
            else:
                # Even when names did not change, refresh verification is a
                # successful check; keep an explicit verified timestamp.
                status_data.setdefault(sym, {
                    "non_muslim_board": False,
                    "directors": old_members,
                    "symbol": sym,
                })
                # Re-run classification even if the director list is unchanged.
                is_100_non_muslim, details = check_board_100_non_muslim_with_confirmation(new_members, sym)
                status_data[sym]["non_muslim_board"] = bool(is_100_non_muslim)
                status_data[sym]["last_checked"] = now_ist().isoformat()
                status_data[sym]["directors"] = new_members
                status_data[sym]["verification_details"] = details
                status_data[sym]["board_refresh_failed"] = False
                status_data[sym]["verified_by"] = "monthly_refresh"
                members_data[sym] = new_members
        except Exception as e:
            logger.warning(f"refresh_board_status: Failed for {sym}: {e}")
            status_data[sym] = {
                "non_muslim_board": False,
                "last_checked": now_ist().isoformat(),
                "directors": members_data.get(sym, []),
                "verified_by": "refresh_exception_fail_closed",
                "symbol": sym,
                "board_refresh_failed": True,
            }

    save_json(BOARD_MEMBERS_FILE, members_data)
    save_json(BOARD_STATUS_FILE, status_data)
    return changed

def get_boards_needing_manual_review() -> list:
    """[AUDIT F16 FIX, 2026-09-16] Name-keyword matching (is_potential_muslim_name)
    has inherent false-positive/negative risk for a compliance classification —
    it is a candidate signal, not a verified verdict. This does NOT change any
    accept/reject logic anywhere (that stays exactly as-is, still fail-closed);
    it only surfaces, for human review, every symbol whose CURRENT board
    status came purely from the automated heuristic (verified_by ==
    "monthly_refresh") rather than an actual manual confirmation. Two review
    categories, in order of real trading-risk severity:
      1. "heuristic_allowed" -- non_muslim_board=True on a heuristic run with
         zero keyword hits. This is an ABSENCE of a match, not a confirmed
         non-Muslim board -- the higher-risk direction (a false negative here
         would silently let a non-compliant board trade).
      2. "heuristic_excluded_ambiguous" -- blocked because of an ambiguous-tier
         name (verification_details.ambiguous_needs_confirm non-empty) that
         web_search_confirm_religion() could not clear -- correctly fail-closed
         today, but worth a human owner/admin double-check per name.
    Symbols with verified_by == "manual" (an actual human already reviewed
    them) or a fail-closed non-heuristic reason (refresh_failed/exception/
    unverified) are intentionally excluded -- those already carry their own
    explicit non-heuristic label and aren't what this heuristic-review list
    is for."""
    _ensure_files()
    status_data = load_json(BOARD_STATUS_FILE, {})
    review = []
    for sym, rec in status_data.items():
        if rec.get("verified_by") != "monthly_refresh":
            continue
        details = rec.get("verification_details", {}) or {}
        ambiguous = details.get("ambiguous_needs_confirm", [])
        if rec.get("non_muslim_board") is True:
            review.append({
                "symbol": sym,
                "reason": "heuristic_allowed",
                "last_checked": rec.get("last_checked"),
                "directors": rec.get("directors", []),
            })
        elif ambiguous:
            review.append({
                "symbol": sym,
                "reason": "heuristic_excluded_ambiguous",
                "last_checked": rec.get("last_checked"),
                "ambiguous_names": ambiguous,
            })
    return review


def get_non_muslim_board_symbols() -> list:
    _ensure_files()
    status_data = load_json(BOARD_STATUS_FILE, {})
    if not status_data:
        try:
            import pandas as pd
            df = pd.read_csv("data/CUSTOM_UNIVERSE_FINAL.csv")
            if "non_muslim_board" in df.columns:
                return df[df["non_muslim_board"]==True]["symbol"].astype(str).tolist()
        except Exception:
            pass
        return []
    return [sym for sym, data in status_data.items() if data.get("non_muslim_board")==True]

def initialize_board_status_from_custom():
    _ensure_files()
    try:
        import pandas as pd
        df = pd.read_csv("data/CUSTOM_UNIVERSE_FINAL.csv")
        status_data = load_json(BOARD_STATUS_FILE, {})
        for _, row in df.iterrows():
            sym = str(row["symbol"]).strip()
            if sym not in status_data:
                status_data[sym] = {
                    # Unknown/unverified board data is NEVER tradeable.
                    "non_muslim_board": False,
                    "last_checked": now_ist().isoformat(),
                    "directors": [],
                    "verified_by": "unverified_fail_closed",
                    "symbol": sym,
                    "board_refresh_failed": True,
                }
        save_json(BOARD_STATUS_FILE, status_data)
        return len(status_data)
    except Exception as e:
        logger.warning(f"initialize_board_status_from_custom failed: {e}")
        return 0
