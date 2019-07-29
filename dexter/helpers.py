import re

from webhelpers2.html import literal, lit_sub, HTML
from webhelpers2.html.tools import _universal_newline_rx, text_to_html as wh_format_paragraphs

newlines_re = re.compile(R"\n+")

def format_paragraphs(text):
    """Convert text to HTML paragraphs.

    ``text``:
        the text to convert.  Split into paragraphs at blank lines (i.e.,
        wherever one or more consecutive newlines appear), and wrap each
        paragraph in a <p>.
    """
    if text is None:
        return literal("")
    text = lit_sub(_universal_newline_rx, "\n", text)

    # ensure all newlines are double
    text = lit_sub(newlines_re, "\n\n", text)

    return wh_format_paragraphs(text)

def source_icon(source):
    if source == 'person':
        return 'fa-user'

    if source == 'child':
        return 'fa-child'

    if source == 'secondary':
        return 'fa-file-o'

def country_flag(country, **kwargs):
    if country:
        return HTML.tag('img',
                src="/public/images/flags/{}.png".format(country.code),
                title=country.name,
                **kwargs)
    else:
        return None

def body_tag_args():
    from flask_login import current_user

    classes = []
    args = {}

    if current_user.is_authenticated:
        classes.append('loggedin')
        args['dataUserName'] = current_user.full_name()
        args['dataUserEmail'] = current_user.email
        args['dataUserId'] = current_user.id

    args['class_'] = ' '.join(classes)
    return args
