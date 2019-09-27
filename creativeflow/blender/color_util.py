"""
Color-related utilities that are specific to Creative Flow data generation pipeline, i.e. for random color selection
or color selection from a list of color themes mined online, etc.
"""

import random
import colorsys


def parse_hsv_bounds(hbound_str, sbound_str, vbound_str):
    def _parse_vals(in_str):
        v = [float(x) for x in hbound_str.strip().split(',')]
        if len(v) != 2:
            raise RuntimeError('Invalid CSV value of two numbers: %s' % in_str)
        if v[0] > 1.0 or v[0] < 0.0 or v[1] > 1.0 or v[1] < 0.0:
            raise RuntimeError('HSV values must be in range [0,1], got %s' % in_str)
        return v

    try:
        h_val = _parse_vals(hbound_str)
        s_val = _parse_vals(sbound_str)
        v_val = _parse_vals(vbound_str)
        return {'hue': h_val, 'sat': s_val, 'val': v_val}
    except Exception as e:
        raise RuntimeError('Failed to parse HSV bounds with error %s' % str(e))


def __are_bounds_trivial(bounds):
    for k, v in bounds.items():
        if v[0] > 0.0 or v[1] < 1.0:
            return False
    return True


def make_color_getter(color_str, max_colors=-1):
    choices = [[float(c)/255.0 for c in x.split(',')] for x in color_str.strip().split()]
    random.shuffle(choices)
    if 0 < max_colors < len(choices):
        choices = choices[0:max_colors]

    return make_color_getter_from_choices(choices)


def make_random_color_getter():
    ncolors = random.randint(4, 15)

    s_mu = random.normalvariate(mu=0.8, sigma=0.2)
    choices = [get_random_color(s_mu=s_mu, s_sigma=0.05) for c in range(ncolors)]

    return make_color_getter_from_choices(choices)


def make_color_getter_from_choices(choices):
    print('Color choices:')
    print(choices)

    def get_color():
        res = choices[random.randint(0, len(choices) - 1)]
        return res

    def get_color_norep():
        get_color_norep.index = (get_color_norep.index + 1) % len(choices)
        return choices[get_color_norep.index]
    get_color_norep.index = 0

    return get_color if random.random() > 0.5 else get_color_norep


def get_random_color(s_mu=0.8, s_sigma=0.2, prob_dark=0.4, bounds=None):
    if bounds and not __are_bounds_trivial(bounds):
        return get_random_color_bounded(bounds)
    else:
        return get_random_color_fullrange(s_mu, s_sigma, prob_dark)


def get_random_color_fullrange(s_mu, s_sigma, prob_dark):
    h = random.random()
    s = min(1.0, max(0.0, random.normalvariate(mu=s_mu, sigma=s_sigma)))
    v = min(1.0, max(0.0, (random.normalvariate(mu=0.2, sigma=0.1)
                           if random.random() < prob_dark else
                           random.normalvariate(mu=0.75, sigma=0.2))))

    return colorsys.hsv_to_rgb(h, s, v)


def get_random_color_bounded(bounds):
    h = random.uniform(bounds['hue'][0], bounds['hue'][1])
    s = random.uniform(bounds['sat'][0], bounds['sat'][1])
    v = random.uniform(bounds['val'][0], bounds['val'][1])
    return colorsys.hsv_to_rgb(h, s, v)
