import comfy
import torch
from comfy.k_diffusion import sampling as k_diffusion_sampling

# from comfy.samplers import normal_scheduler


# These two may be wrong for v-pred... but it seems to work?
# Copied from k_diffusion
def sigma_to_t(ms, sigma, quantize=True):
    log_sigmas = ms.log_sigmas.cpu()
    log_sigma = sigma.log()
    dists = log_sigma - log_sigmas[:, None]
    if quantize:
        return dists.abs().argmin(dim=0).view(sigma.shape)
    low_idx = dists.ge(0).cumsum(dim=0).argmax(dim=0).clamp(max=log_sigmas.shape[0] - 2)
    high_idx = low_idx + 1
    low, high = log_sigmas[low_idx], log_sigmas[high_idx]
    w = (low - log_sigma) / (low - high)
    w = w.clamp(0, 1)
    t = (1 - w) * low_idx + w * high_idx
    return t.view(sigma.shape)


# Copied from k_diffusion
def t_to_sigma(ms, t):
    t = t.float()
    low_idx, high_idx, w = t.floor().long(), t.ceil().long(), t.frac()
    log_sigma = (1 - w) * ms.log_sigmas[low_idx] + w * ms.log_sigmas[high_idx]
    return log_sigma.exp()


def get_sigmas_karras(_model, n, s_min, s_max, device):
    return k_diffusion_sampling.get_sigmas_karras(n, s_min, s_max, device=device)


def get_sigmas_exponential(_model, n, s_min, s_max, device):
    return k_diffusion_sampling.get_sigmas_exponential(n, s_min, s_max, device=device)


def normal_scheduler(model, steps, s_min, s_max, sgm=False):
    """
    Pulled from comfy.samplers.normal_scheduler
    """
    ms = model.model_sampling
    start = ms.timestep(torch.tensor(s_max))
    end = ms.timestep(torch.tensor(s_min))

    if sgm:
        timesteps = torch.linspace(start, end, steps + 1)[:-1]
    else:
        timesteps = torch.linspace(start, end, steps)

    sigs = (*(ms.sigma(timesteps[x]) for x in range(len(timesteps))), 0.0)
    return torch.FloatTensor(sigs)


def get_sigmas_normal(model, n, s_min, s_max, device):
    return normal_scheduler(model, n, s_min, s_max).to(device)


def get_sigmas_simple(model, n, s_min, s_max, device):
    ms = model.model_sampling
    min_idx = torch.argmin(torch.abs(ms.sigmas - s_min))
    max_idx = torch.argmin(torch.abs(ms.sigmas - s_max))
    sigmas_slice = ms.sigmas[min_idx:max_idx]
    ss = len(sigmas_slice) / n
    sigs = (
        float(s_max),
        *(float(sigmas_slice[-(1 + int(x * ss))]) for x in range(1, n - 1)),
        float(s_min),
        0.0,
    )
    return torch.tensor(sigs, device=device)


def get_sigmas_ddim_uniform(model, n, s_min, s_max, device):
    ms = model.model_sampling
    t_min, t_max = sigma_to_t(ms, torch.tensor([s_min, s_max], device=device))
    ddim_timesteps = torch.linspace(t_max, t_min, n, dtype=torch.int16, device=device)
    sigs = (*(t_to_sigma(ms, min(ts, 999)) for ts in ddim_timesteps), 0.0)
    return torch.tensor(sigs, device=device)


def get_sigmas_sgm_uniform(model, n, s_min, s_max, device):
    return normal_scheduler(model, n, s_min, s_max, sgm=True).to(device)


def get_sigmas_simple_test(model, n, s_min, s_max, device):
    ms = model.model_sampling
    min_idx = torch.argmin(torch.abs(ms.sigmas - s_min))
    max_idx = torch.argmin(torch.abs(ms.sigmas - s_max))
    sigmas_slice = ms.sigmas[min_idx:max_idx]
    ss = len(sigmas_slice) / n
    sigs = (*(float(sigmas_slice[-(1 + int(x * ss))]) for x in range(n)), 0.0)
    return torch.tensor(sigs, device=device)


def get_comfy_scheduler_fn(name):
    return (
        lambda model,
        steps,
        _smin,
        _smax,
        device="cpu": comfy.samplers.calculate_sigmas(
            model.model_sampling,
            name,
            steps,
        ).to(device)
    )


RESTART_SCHEDULER_MAPPING = {
    "normal": get_sigmas_normal,
    "karras": get_sigmas_karras,
    "exponential": get_sigmas_exponential,
    "simple": get_sigmas_simple,
    "ddim_uniform": get_sigmas_ddim_uniform,
    "sgm_uniform": get_sigmas_sgm_uniform,
    "simple_test": get_sigmas_simple_test,
}

NORMAL_SCHEDULER_MAPPING = {
    k: get_comfy_scheduler_fn(k) for k in comfy.samplers.SCHEDULER_NAMES
} | {
    "simple_test": get_sigmas_simple_test,
}
