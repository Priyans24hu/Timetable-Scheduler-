from django import template
register = template.Library()

@register.filter
def dictKey(d, k):
    '''Returns the given key from a dictionary.'''

    return ', '.join(d[k]) or ''

@register.filter
def get_item(dictionary, key):
    """
    Template filter to access dictionary items by key
    Usage: {{ mydict|get_item:key }}
    """
    try:
        return dictionary.get(key, '')
    except (AttributeError, TypeError):
        return ''


@register.simple_tag
def sub(s, d, w, t):
    '''Returns the subject-teacher-room for a department, weekday and time period'''
    for c in s:
        if c.department.dept_name == d and c.meeting_time.day == w and c.meeting_time.time == t:
            room_info = f'Room {c.room.r_number}' if c.room else 'Room TBD'
            return f'{c.course.course_name} ({c.instructor.name})<br>{c.section}<br>{room_info}'

    return ''

@register.tag
def active(parser, token):
    args = token.split_contents()
    template_tag = args[0]
    if len(args) < 2:
        raise (template.TemplateSyntaxError, f'{template_tag} tag requires at least one argument')
    return NavSelectedNode(args[1:])

class NavSelectedNode(template.Node):
    def __init__(self, patterns):
        self.patterns = patterns
    def render(self, context):
        path = context['request'].path
        for p in self.patterns:
            pValue = template.Variable(p).resolve(context)
            if path == pValue:
                return 'active'
        return ''