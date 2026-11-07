"""Doc in Hindi.

Doc's answers are built from a fixed set of sentence patterns filled with values from the case, so
each pattern has an exact Hindi counterpart here, and finding titles have Hindi names. Numbers,
names and values pass through unchanged, so a Hindi answer can't say anything the English one
doesn't. Free text written by the checks (explanations, suggested checks) has no fixed pattern, so
it stays in English with a note saying so.

Hindi questions are mapped to the English question they ask, by keywords, before the rules run.
"""
from __future__ import annotations

import re
from collections.abc import Callable

STATUS = {"Potential manipulation": "संभावित हेरफेर", "Inconsistency": "असंगति", "Observation": "अवलोकन"}
RISK = {"high": "उच्च", "medium": "मध्यम", "low": "निम्न", "undetermined": "अनिर्धारित"}
DOCS = {
    "salary slip": "वेतन पर्ची", "bank statement": "बैंक विवरण", "application form": "आवेदन पत्र", "id proof": "पहचान पत्र",
    "address proof": "पते का प्रमाण", "declaration": "घोषणा पत्र", "unknown": "दस्तावेज़",
}
FIELDS = {
    "net pay": "शुद्ध वेतन", "gross pay": "सकल वेतन", "declared monthly income": "घोषित मासिक आय", "date of birth": "जन्म तिथि",
    "person name": "नाम", "address": "पता", "pan number": "पैन", "id number": "पहचान संख्या",
    "bank account number": "बैंक खाता संख्या", "employer name": "नियोक्ता का नाम", "designation": "पद", "phone": "मोबाइल नंबर",
    "email": "ईमेल", "loan amount": "ऋण राशि", "date of joining": "कार्यग्रहण तिथि", "ifsc": "IFSC",
}
TITLES = {
    "Net pay in figures differs from net pay in words": "शुद्ध वेतन अंकों और शब्दों में अलग है",
    "Running balance breaks in the transaction table": "लेन-देन तालिका में चालू शेष का क्रम टूटता है",
    "Net pay does not equal gross pay minus deductions": "शुद्ध वेतन, सकल वेतन घटा कटौतियों के बराबर नहीं है",
    "Bank account number differs across documents": "दस्तावेज़ों में बैंक खाता संख्या अलग है",
    "Subtle address variant across documents": "दस्तावेज़ों में पते में हल्का अंतर",
    "Declared income is above what the salary slip shows": "घोषित आय वेतन पर्ची में दिखाई गई आय से अधिक है",
    "Date of birth differs across documents": "दस्तावेज़ों में जन्म तिथि अलग है",
    "Employer name differs across documents": "दस्तावेज़ों में नियोक्ता का नाम अलग है",
    "Joining date differs across documents": "दस्तावेज़ों में कार्यग्रहण तिथि अलग है",
    "PAN differs across documents": "दस्तावेज़ों में पैन अलग है",
    "Different names across documents": "दस्तावेज़ों में अलग-अलग नाम",
    "Net pay matches only one of the monthly salary credits": "शुद्ध वेतन मासिक वेतन जमा में से केवल एक से मेल खाता है",
    "Net pay on the salary slip does not match the bank credit": "वेतन पर्ची का शुद्ध वेतन बैंक में जमा राशि से मेल नहीं खाता",
    "The PDF was modified after it was created": "PDF बनने के बाद उसमें बदलाव किया गया",
    "Visible text differs from the PDF text layer": "दिखाई देने वाला पाठ PDF की टेक्स्ट परत से अलग है",
    "The date of birth doesn't match the registry record": "जन्म तिथि रजिस्टर के रिकॉर्ड से मेल नहीं खाती",
    "The name doesn't match the registry record": "नाम रजिस्टर के रिकॉर्ड से मेल नहीं खाता",
    "This ID number isn't in the registry": "यह पहचान संख्या रजिस्टर में नहीं है",
    "Value is off its column edge": "मान अपने कॉलम की सीध से हटा हुआ है",
    "Two regions of this page look copied from one another": "इस पृष्ठ के दो हिस्से एक-दूसरे की नकल लगते हैं",
    "Compression response differs for this text": "इस पाठ पर संपीड़न का असर अलग है",
    "Typography differs from other text on the page": "अक्षरों की बनावट पृष्ठ के बाकी पाठ से अलग है",
    "Background is noisier than the surrounding paper": "पृष्ठभूमि आसपास के कागज़ से अधिक दानेदार है",
    "Background is smoother than the surrounding paper": "पृष्ठभूमि आसपास के कागज़ से अधिक चिकनी है",
    "Photo differs from the surrounding page": "फ़ोटो आसपास के पृष्ठ से अलग है",
    "The same signature pixels appear on two documents": "दो दस्तावेज़ों पर हस्ताक्षर के एक जैसे पिक्सेल हैं",
    "An object was painted over existing text": "मौजूदा पाठ के ऊपर कुछ बनाया गया है",
    "Background compresses differently here": "यहाँ पृष्ठभूमि का संपीड़न अलग है",
    "Image metadata names image-editing software": "छवि के मेटाडेटा में छवि-संपादन सॉफ़्टवेयर का नाम है",
    "Image was saved after it was captured": "छवि खींचे जाने के बाद फिर से सहेजी गई",
    "No signature ink found near this signature label": "हस्ताक्षर लेबल के पास स्याही नहीं मिली",
    "PDF metadata records disagree about the creating software": "PDF मेटाडेटा में बनाने वाले सॉफ़्टवेयर के बारे में मतभेद है",
    "Paper behind this value is smoother than the paper around it": "इस मान के पीछे का कागज़ आसपास से अधिक चिकना है",
    "Signature placement looks unusual": "हस्ताक्षर की जगह असामान्य लगती है",
    "Text layer holds words that aren't visible": "टेक्स्ट परत में ऐसे शब्द हैं जो दिखाई नहीं देते",
    "Text sits on a patch of different background": "पाठ अलग पृष्ठभूमि के टुकड़े पर है",
    "The PDF was last written by different software from the one that created it": "PDF को बनाने वाले से अलग सॉफ़्टवेयर ने आख़िरी बार लिखा",
    "The PDF was saved more than once": "PDF एक से अधिक बार सहेजी गई",
    "The PDF's modification date is earlier than its creation date": "PDF की बदलाव तिथि उसके बनने की तिथि से पहले की है",
    "This area changed in a later saved revision of the PDF": "यह हिस्सा PDF के बाद के संस्करण में बदला गया",
    "This file came through different software from the others": "यह फ़ाइल बाकी से अलग सॉफ़्टवेयर से होकर आई है",
    "This value uses a font that's rare on the page": "इस मान का फ़ॉन्ट पृष्ठ पर दुर्लभ है",
    "Word sits off the baseline of its row": "शब्द अपनी पंक्ति की आधार रेखा से हटा हुआ है",
    "The page has an editable form field": "पृष्ठ पर संपादन योग्य फ़ॉर्म फ़ील्ड है",
    "An earlier application in the same name": "इसी नाम से एक पुराना आवेदन",
    "A contextual check could not complete": "एक संदर्भ जाँच पूरी नहीं हो सकी",
    "A cross-document check could not complete": "एक दस्तावेज़-तुलना जाँच पूरी नहीं हो सकी",
}

GUIDE = {
    "On the home page": "होम पेज पर केस का नाम लिखें और Start a new case दबाएँ। फिर आवेदन के सभी दस्तावेज़ खींचकर डालें और Check these documents "
                        "दबाएँ। PNG, JPG और PDF सभी चलते हैं। या पहले कोई उदाहरण खोलकर देखें कि यह कैसा दिखता है।",
    "There are three kinds of finding": "निष्कर्ष तीन तरह के होते हैं। अवलोकन कोई मापी गई बात है, और अकेले उसका ख़ास अर्थ नहीं होता। असंगति दो ऐसे मान हैं "
                                        "जिन्हें मेल खाना चाहिए पर नहीं खाते। संभावित हेरफेर इस बात का संकेत है कि दस्तावेज़ बदला गया हो सकता है। "
                                        "यह आपके जाँचने की संभावना है, कोई निष्कर्ष नहीं।",
    "Open a finding and choose": "कोई निष्कर्ष खोलें और चुनें: Confirm, अगर आप मानते हैं कि समस्या असली है; Dismiss, अगर आपने जाँच ली है और सब ठीक है; "
                                 "या Escalate, इसे किसी वरिष्ठ को भेजने के लिए। आप एक नोट भी जोड़ सकते हैं। हर निर्णय History टैब में सहेजा जाता है।",
    "The risk level only helps": "जोखिम स्तर केवल यह तय करने में मदद करता है कि पहले क्या देखना है। बदलाव के मज़बूत प्रमाण या कई टकराव हों तो यह उच्च होता है, "
                                 "कम या कमज़ोर हों तो मध्यम, वरना निम्न। यह किसी के बारे में कोई निर्णय नहीं है।",
    "Open the Report tab": "Report टैब खोलें और ऊपर Download PDF या Download JSON दबाएँ। इसमें दस्तावेज़, पढ़े गए मान, टकराव, दृश्य जाँचें, "
                           "प्रमाण और सारांश शामिल हैं।",
    "The History tab lists": "History टैब में केस पर हुई हर घटना दर्ज है, और हर प्रविष्टि पिछली से जुड़ी हुई है। Verify integrity सबकी दोबारा जाँच करता है "
                             "और बदली गई पहली प्रविष्टि का नाम बताता है। Try editing an entry इसे काम करते हुए दिखाता है, और बाद में आप इसे वापस कर सकते हैं।",
    "In the Findings tab": "Findings टैब में Show मेनू से पृष्ठ पर दिखने वाली चीज़ बदलती है। Error level analysis और Noise residual उन हिस्सों को "
                           "उभारते हैं जो बाकी से अलग व्यवहार करते हैं। ये केवल संकेत हैं, और सामान्य दस्तावेज़ भी अक्सर चमकते हैं।",
    "Use the moon or sun": "ऊपर दाईं ओर चाँद या सूरज वाला बटन दबाएँ।",
    "Drag me anywhere": "मुझे कहीं भी खींचकर ले जाएँ। छिपाने के लिए इस चैट के ऊपर Hide दबाएँ, और वापस लाने के लिए Show Doc दबाएँ।",
    "I can read printed English": "मैं छपी हुई अंग्रेज़ी और हिंदी पढ़ सकता हूँ, और हिंदी में उत्तर दे सकता हूँ। हाथ की लिखावट भरोसे से नहीं पढ़ी जाती, "
                                  "इसलिए उन मानों को आँख से जाँचें। मैं नहीं बता सकता कि किसने हस्ताक्षर किए, और मैं असली सरकारी या बैंक रिकॉर्ड नहीं "
                                  "जाँचता। अभी तक असली दस्तावेज़ों पर कुछ भी परखा नहीं गया है। पूरी सूची About पेज पर है।",
    "I'm Doc, a guide": "मैं Doc हूँ, इस ऐप का मार्गदर्शक। मैं बता सकता हूँ कि जाँचों में क्या मिला, मान ढूँढ सकता हूँ, और दिखा सकता हूँ कि चीज़ें कहाँ हैं। "
                        "मैं कोई निष्कर्ष बदल नहीं सकता और न कोई निर्णय ले सकता हूँ। पूछकर देखें कि मुझे क्या मिला, या किसी निष्कर्ष को उसके "
                        "नंबर से समझाने को कहें, जैसे #2।",
    "Open a finding and press Draft verification request": "कोई निष्कर्ष खोलें और Draft verification request दबाएँ। मैं दस्तावेज़ जारी करने वाले को एक पत्र "
                        "लिखूँगा, जिसमें ठीक उन्हीं मानों की पुष्टि माँगी जाएगी जिन पर संदेह है। आप उसे जाँचकर ख़ुद भेजते हैं: यह ऐप कुछ भी नहीं भेजता।",
}

SUGGESTIONS = {
    "What did you find?": "आपको क्या मिला?", "What should I look at first?": "मुझे पहले क्या देखना चाहिए?",
    "How do I download the report?": "रिपोर्ट कैसे डाउनलोड करूँ?", "What do the labels mean?": "लेबल का क्या अर्थ है?",
    "What can you do?": "आप क्या कर सकते हैं?", "What do Confirm and Dismiss do?": "Confirm और Dismiss क्या करते हैं?",
    "How is the risk level set?": "जोखिम स्तर कैसे तय होता है?", "What does Verify integrity do?": "Verify integrity क्या करता है?",
    "How do I start?": "शुरू कैसे करूँ?", "Could this be innocent?": "क्या यह निर्दोष हो सकता है?",
    "How do I check this?": "मैं इसकी जाँच कैसे करूँ?", "Explain this finding": "यह निष्कर्ष समझाइए",
    "Show me the strongest evidence": "सबसे मज़बूत प्रमाण दिखाइए", "Do the documents conflict?": "क्या दस्तावेज़ आपस में टकराते हैं?",
    "Which document looks suspicious?": "किस दस्तावेज़ में समीक्षा के लिए सबसे अधिक है?", "Has this been seen before?": "क्या ये विवरण पहले देखे गए हैं?",
    "Draft a verification letter": "सत्यापन पत्र का मसौदा बनाइए",
}
LINKS = {
    "Show it in the document": "दस्तावेज़ में दिखाएँ", "Review findings": "निष्कर्ष देखें", "Go to the overview": "ओवरव्यू पर जाएँ",
    "Compare side by side": "साथ-साथ तुलना करें", "Open the other application": "दूसरा आवेदन खोलें",
}

# Hindi question words to the English question they ask. First match wins, so specific comes first.
_INTENTS: list[tuple[str, str]] = [
    (r"धोखा|नकली|जाली|फ़र्ज़ी|फर्जी|असली है|स्वीकार|अस्वीकार|मंज़ूर|भरोसा", "is this fake"),
    (r"पहले देख|दूसरे आवेदन|दूसरे केस|दोहरा|दोबारा आवेदन", "has this been seen before"),
    (r"पत्र|मसौदा|चिट्ठी", "draft a verification letter"),
    (r"निर्दोष|मासूम|सामान्य कारण", "could this be innocent"),
    (r"जाँच कैसे|जांच कैसे|पुष्टि कैसे|सत्यापित", "how do i check this"),
    (r"समझा", "explain this finding"),
    (r"मज़बूत|मजबूत", "show me the strongest evidence"),
    (r"संदिग्ध|सबसे अधिक|सबसे ज़्यादा", "which document looks suspicious"),
    (r"शुरू कैसे|केस कैसे|अपलोड|दस्तावेज़ कैसे जोड़", "how do i start"),
    (r"पहले क्या|पहले देखना|प्राथमिकता|शुरुआत", "what should i look at first"),
    (r"टकरा|मेल नहीं|विरोध", "do the documents conflict"),
    (r"रिपोर्ट|डाउनलोड", "how do i download the report"),
    (r"लेबल|रंग|अवलोकन|असंगति|हेरफेर", "what do the labels mean"),
    (r"जोखिम", "how is the risk level set"),
    (r"इतिहास|अखंडता|history", "what does verify integrity do"),
    (r"शुद्ध वेतन|वेतन|तनख़्वाह|तनख्वाह", "what's the net pay"),
    (r"जन्म", "what's the date of birth"),
    (r"खाता", "what's the bank account number"),
    (r"पैन", "what's the pan"),
    (r"नियोक्ता|कंपनी", "who is the employer"),
    (r"पता", "what's the address"),
    (r"मोबाइल|फ़ोन|फोन", "what's the phone"),
    (r"क्या मिला|परिणाम|नतीजे|सारांश|निष्कर्ष", "what did you find"),
    (r"मदद|आप कौन|क्या कर सकते|कैसे काम", "what can you do"),
]
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def to_english(question: str) -> str:
    """The English question a Hindi one asks. English questions pass through."""
    q = question.strip()
    reverse = {v: k for k, v in SUGGESTIONS.items()}
    if q in reverse:
        return reverse[q]
    if not _DEVANAGARI.search(q):
        return q
    number = re.search(r"#\s*(\d+)|(\d+)", q)
    for pattern, english in _INTENTS:
        if re.search(pattern, q):
            if number:
                n = number.group(1) or number.group(2)
                return f"{english.replace('this finding', '').strip()} #{n}".strip()
            return english
    if number:
        return f"explain #{number.group(1) or number.group(2)}"
    return q


# ---------------------------------------------------------------- answer patterns
class _NoHindi(Exception):
    """A title with no Hindi name: the line stays in English, under the note."""


def _title(text: str) -> str:
    text = text.strip()
    m = re.match(r"(.*?)\s*\((\d+) signals agree\)$", text)
    if m:
        return f"{_title(m.group(1))} ({m.group(2)} संकेत सहमत)"
    m = re.match(r"(\d+) details? from this application appears? in another one$", text)
    if m:
        return f"इस आवेदन के {m.group(1)} विवरण किसी दूसरे आवेदन में भी हैं"
    m = re.match(r"Expected fields not found on this (.+)$", text)
    if m:
        return f"इस {_doc(m.group(1))} पर अपेक्षित फ़ील्ड नहीं मिले"
    if text not in TITLES:
        raise _NoHindi(text)
    return TITLES[text]


def _doc(text: str) -> str:
    return DOCS.get(text.strip().lower(), text)


def _risk(text: str) -> str:
    return RISK.get(text.strip().lower(), text)


def _field(text: str) -> str:
    return FIELDS.get(text.strip().lower(), text)


Rule = tuple[re.Pattern[str], Callable[[re.Match[str]], str]]


def _r(pattern: str, fn: Callable[[re.Match[str]], str]) -> Rule:
    return re.compile(pattern + r"$"), fn


def _parts(text: str) -> str:
    out = []
    for n, kind in re.findall(r"(\d+) (potential manipulations?|inconsistency|inconsistencies)", text):
        out.append(f"{n} संभावित हेरफेर" if kind.startswith("potential") else f"{n} असंगति" if n == "1" else f"{n} असंगतियाँ")
    return " और ".join(out)


_VERDICT_HEAD = ("I can't tell you that, and neither can these checks. They point out what looks odd, and a person has to look into it, "
                 "usually by asking the issuer for the original.")
_VERDICT_HI = ("यह मैं नहीं बता सकता, और न ही ये जाँचें बता सकती हैं। ये केवल वह दिखाती हैं जो असामान्य लगता है, और किसी व्यक्ति को इसकी जाँच "
               "करनी होती है, आमतौर पर जारीकर्ता से मूल दस्तावेज़ माँगकर।")

RULES: list[Rule] = [
    _r(r"#(\d+) could be innocent if:", lambda m: f"#{m[1]} इन स्थितियों में निर्दोष हो सकता है:"),
    _r(r"To check #(\d+):", lambda m: f"#{m[1]} की जाँच के लिए:"),
    _r(r"#(\d+) is marked (Potential manipulation|Inconsistency|Observation): (.+)\.",
       lambda m: f"#{m[1]} को {STATUS[m[2]]} चिह्नित किया गया है: {_title(m[3])}।"),
    _r(r"This is for you to check, not a conclusion\.", lambda m: "यह आपके जाँचने के लिए है, कोई निष्कर्ष नहीं।"),
    _r(re.escape(_VERDICT_HEAD) + r" Here, (\d+) findings? still needs? checking, and the risk level is (\w+)\.",
       lambda m: f"{_VERDICT_HI} यहाँ {m[1]} निष्कर्षों की अभी जाँच बाकी है, और जोखिम स्तर {_risk(m[2])} है।"),
    _r(re.escape(_VERDICT_HEAD) + r" Here, nothing stood out, but that doesn't prove anything either\.",
       lambda m: f"{_VERDICT_HI} यहाँ कुछ भी असामान्य नहीं दिखा, लेकिन इससे भी कुछ सिद्ध नहीं होता।"),
    _r(re.escape(_VERDICT_HEAD), lambda m: _VERDICT_HI),
    _r(r"I can't find a finding #(\d+) here\. There (?:is|are) (\d+)\.", lambda m: f"मुझे यहाँ निष्कर्ष #{m[1]} नहीं मिला। कुल {m[2]} निष्कर्ष हैं।"),
    _r(r"Open a case first, and I can tell you about its results\. You could try one of the examples on the home page\.",
       lambda m: "पहले कोई केस खोलें, फिर मैं उसके परिणाम बता सकता हूँ। आप होम पेज पर कोई उदाहरण आज़मा सकते हैं।"),
    _r(r"I'm still checking these documents\. Ask me again in a moment\.", lambda m: "मैं अभी इन दस्तावेज़ों की जाँच कर रहा हूँ। थोड़ी देर में फिर पूछें।"),
    _r(r"These documents haven't been checked yet\. Add them on the Overview tab, then press Check these documents\.",
       lambda m: "इन दस्तावेज़ों की अभी जाँच नहीं हुई है। इन्हें Overview टैब में जोड़ें, फिर Check these documents दबाएँ।"),
    _r(r"None of these files could be read, so nothing was checked\. The Overview tab says why for each one\.",
       lambda m: "इनमें से कोई भी फ़ाइल पढ़ी नहीं जा सकी, इसलिए कुछ भी जाँचा नहीं गया। Overview टैब में हर फ़ाइल का कारण दिया गया है।"),
    _r(r"Nothing here needs attention, so there's no strong signal to point at\. That doesn't prove the documents are genuine\.",
       lambda m: "यहाँ किसी चीज़ पर ध्यान देने की ज़रूरत नहीं है, इसलिए कोई मज़बूत संकेत नहीं है। इससे यह सिद्ध नहीं होता कि दस्तावेज़ असली हैं।"),
    _r(r"The strongest signal is #(\d+): (.+), at (\d+)% confidence\.",
       lambda m: f"सबसे मज़बूत संकेत #{m[1]} है: {_title(m[2])}, {m[3]}% विश्वास के साथ।"),
    _r(r"Strong only means the check is sure about what it measured\. It still needs a person to explain it\.",
       lambda m: "मज़बूत का अर्थ केवल इतना है कि जाँच ने जो मापा, उसके बारे में वह आश्वस्त है। इसे समझाने के लिए अब भी किसी व्यक्ति की ज़रूरत है।"),
    _r(r"None of the documents has anything that needs attention\. That doesn't prove they're genuine\.",
       lambda m: "किसी भी दस्तावेज़ में ध्यान देने लायक कुछ नहीं है। इससे यह सिद्ध नहीं होता कि वे असली हैं।"),
    _r(r"The (.+) has the most to review, with (\d+) findings?:", lambda m: f"{_doc(m[1])} में समीक्षा के लिए सबसे अधिक है, {m[2]} निष्कर्ष:"),
    _r(r"That tells you where to look first\. It isn't a judgement that anything on it is wrong\.",
       lambda m: "इससे पता चलता है कि पहले कहाँ देखना है। इसका अर्थ यह नहीं कि उसमें कुछ गलत है।"),
    _r(r"Nothing here needs attention\. A clean result doesn't prove the documents are genuine, though\.",
       lambda m: "यहाँ किसी चीज़ पर ध्यान देने की ज़रूरत नहीं है। फिर भी, साफ़ परिणाम से यह सिद्ध नहीं होता कि दस्तावेज़ असली हैं।"),
    _r(r"I'd start with #(\d+): (.+)\.", lambda m: f"मैं #{m[1]} से शुरू करूँगा: {_title(m[2])}।"),
    _r(r"This case is (\w+) risk because of what it found:", lambda m: f"इस केस का जोखिम स्तर {_risk(m[1])} है, इन निष्कर्षों के कारण:"),
    _r(r"This case is (\w+) risk because of what it found, and nothing here needs attention\.",
       lambda m: f"इस केस का जोखिम स्तर {_risk(m[1])} है, और यहाँ किसी चीज़ पर ध्यान देने की ज़रूरत नहीं है।"),
    _r(r"The level is only for deciding what to look at first\.", lambda m: "यह स्तर केवल यह तय करने के लिए है कि पहले क्या देखना है।"),
    _r(r"I didn't find conflicts between these documents\. That doesn't prove they're genuine\.",
       lambda m: "मुझे इन दस्तावेज़ों के बीच कोई टकराव नहीं मिला। इससे यह सिद्ध नहीं होता कि वे असली हैं।"),
    _r(r"The documents disagree in (\d+) ways?:", lambda m: f"दस्तावेज़ {m[1]} बातों में मेल नहीं खाते:"),
    _r(r"Here's the (.+) as read from the documents\.", lambda m: f"दस्तावेज़ों से पढ़ा गया {_field(m[1])}:"),
    _r(r"These were read by a machine\.( These don't all match, so check Compare documents\.)?",
       lambda m: "ये मशीन द्वारा पढ़े गए हैं।" + (" ये सभी मेल नहीं खाते, इसलिए Compare documents देखें।" if m[1] else "")),
    _r(r"I couldn't find a (.+) in these documents\.", lambda m: f"मुझे इन दस्तावेज़ों में {_field(m[1])} नहीं मिला।"),
    _r(r"Nothing on the (.+) needs attention\.", lambda m: f"{_doc(m[1])} पर किसी चीज़ पर ध्यान देने की ज़रूरत नहीं है।"),
    _r(r"On the (.+), (\d+) findings? to look at:", lambda m: f"{_doc(m[1])} पर देखने के लिए {m[2]} निष्कर्ष:"),
    _r(r"Nothing needed attention across (\d+) documents?, and the risk level is (\w+)\. That doesn't prove they're genuine\.",
       lambda m: f"{m[1]} दस्तावेज़ों में किसी चीज़ पर ध्यान देने की ज़रूरत नहीं थी, और जोखिम स्तर {_risk(m[2])} है। इससे यह सिद्ध नहीं होता कि वे असली हैं।"),
    _r(r"Across (\d+) documents?, I found (.+)\. The risk level is (\w+)\.",
       lambda m: f"{m[1]} दस्तावेज़ों में मुझे {_parts(m[2])} मिले। जोखिम स्तर {_risk(m[3])} है।"),
    _r(r"The main ones:", lambda m: "मुख्य निष्कर्ष:"),
    _r(r"- #(\d+): (.+)", lambda m: f"- #{m[1]}: {_title(m[2])}"),
    _r(r"(Salary slip|Bank statement|Application form|Id proof|Address proof|Declaration|Unknown): (.+?)( \(low confidence, please check\))?",
       lambda m: f"{_doc(m[1])}: {m[2]}" + (" (कम विश्वास, कृपया जाँचें)" if m[3] else "")),
    _r(r"I can't give you a reliable answer to that, but here's what the results show\.",
       lambda m: "मैं इसका भरोसेमंद उत्तर नहीं दे सकता, लेकिन परिणाम यह दिखाते हैं:"),
    _r(r"I'm not sure about that one\..*", lambda m: "मुझे इसका पक्का पता नहीं। मैं बता सकता हूँ कि जाँचों में क्या मिला, शुद्ध वेतन जैसा कोई मान ढूँढ "
                                                    "सकता हूँ, किसी निष्कर्ष को उसके नंबर से समझा सकता हूँ, या इस ऐप का उपयोग करना दिखा सकता हूँ।"),
    _r(r"Ask me anything about this app or these documents\.", lambda m: "इस ऐप या इन दस्तावेज़ों के बारे में कुछ भी पूछें।"),
    _r(r"Details from this application also appear in (\d+) other applications?:",
       lambda m: f"इस आवेदन के विवरण {m[1]} दूसरे आवेदनों में भी हैं:"),
    _r(r"- '(.+)'( \(same applicant name\))?: (.+)", lambda m: f"- '{m[1]}'" + (" (इसी नाम से)" if m[2] else "") + f": {_details(m[3])}"),
    _r(r"Repeated details can be innocent, such as a family sharing a phone, so they're for you to check\.",
       lambda m: "दोहराए गए विवरण निर्दोष भी हो सकते हैं, जैसे परिवार का एक ही फ़ोन, इसलिए इनकी जाँच आपको करनी है।"),
    _r(r"Nothing from this application appears in the (\d+) other applications? on this system\.",
       lambda m: f"इस आवेदन का कोई भी विवरण इस सिस्टम के {m[1]} दूसरे आवेदनों में नहीं है।"),
    _r(r"There are no other applications on this system to compare with yet\.",
       lambda m: "तुलना के लिए इस सिस्टम पर अभी कोई दूसरा आवेदन नहीं है।"),
]

_DETAILS = {"applicant photo": "फ़ोटो", "signature": "हस्ताक्षर", "mobile number": "मोबाइल नंबर", "email address": "ईमेल",
            "bank account number": "बैंक खाता संख्या", "PAN": "पैन", "ID number": "पहचान संख्या"}


def _details(text: str) -> str:
    return ", ".join(_DETAILS.get(p.strip(), _DETAILS.get(p.strip().lower(), p.strip())) for p in text.split(","))


def translate_line(line: str) -> str | None:
    """The Hindi for one line of Doc's answer, or None when it has no fixed pattern."""
    if not line.strip():
        return line
    for prefix, hindi in GUIDE.items():
        if line.startswith(prefix):
            return hindi
    for pattern, fn in RULES:
        m = pattern.match(line)
        if m:
            try:
                return fn(m)
            except _NoHindi:
                return None
    return None


ENGLISH_NOTE = "(कुछ पंक्तियाँ अंग्रेज़ी में हैं: वे जाँचों के अपने विवरण हैं, जिनका हिंदी अनुवाद अभी उपलब्ध नहीं है।)"


def translate(reply):
    """Hindi version of a chat Reply. Lines without a fixed pattern stay in English, with a note saying so.

    Machine translation was tried and rejected: a local 7B model produced wrong words and stray scripts,
    and a mistranslated explanation is worse than an English one.
    """
    lines = reply.answer.split("\n")
    out = [translate_line(line) for line in lines]
    english = any(v is None for v in out)
    reply.answer = "\n".join(v if v is not None else line for v, line in zip(out, lines, strict=True))
    if english:
        reply.answer += "\n" + ENGLISH_NOTE
    reply.links = [{**link, "label": _link_label(link["label"])} for link in reply.links]
    reply.suggestions = [SUGGESTIONS.get(s, s) for s in reply.suggestions]
    return reply


def _link_label(label: str) -> str:
    m = re.match(r"Show #(\d+) in the document$", label)
    if m:
        return f"#{m[1]} दस्तावेज़ में दिखाएँ"
    return LINKS.get(label, label)
