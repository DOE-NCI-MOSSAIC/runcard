"""Quickstart: fit a line to noisy data with gradient descent.

The task is deliberately trivial. What matters is the shape of the script:

* ``@experiment`` turns ``conf/config.yaml`` into ``cfg`` and sets up
  logging and a per-run output directory.
* ``log.info("event_name", key=value)`` replaces ``print``.

Run from anywhere::

    uv run python examples/quickstart/train.py
    uv run python examples/quickstart/train.py model.lr=0.9
    uv run python examples/quickstart/train.py -m model.lr=0.1,0.5,4.0
"""

import random
import time

import polars as pl
from omegaconf import DictConfig

from runcard import experiment, get_logger

log = get_logger("train")


def make_data(n_rows: int, seed: int, true_slope: float, noise: float) -> pl.DataFrame:
    """Return a DataFrame of ``y = true_slope * x + noise`` for x in [-1, 1]."""
    rng = random.Random(seed)
    xs = [rng.uniform(-1.0, 1.0) for _ in range(n_rows)]
    ys = [true_slope * x + rng.gauss(0.0, noise) for x in xs]
    return pl.DataFrame({"x": xs, "y": ys})


def mse(df: pl.DataFrame, slope: float) -> float:
    return df.select(((slope * pl.col("x") - pl.col("y")) ** 2).mean()).item()


def gradient(df: pl.DataFrame, slope: float) -> float:
    """d(MSE)/d(slope) = mean(2 * (slope * x - y) * x)."""
    return df.select((2 * (slope * pl.col("x") - pl.col("y")) * pl.col("x")).mean()).item()


@experiment("conf/config.yaml")
def main(cfg: DictConfig) -> None:
    log.info(
        "start",
        n_rows=cfg.data.n_rows,
        seed=cfg.data.seed,
        lr=cfg.model.lr,
        epochs=cfg.model.epochs,
    )

    df = make_data(cfg.data.n_rows, cfg.data.seed, cfg.data.true_slope, cfg.data.noise)
    log.info(
        "data_ready", rows=df.height, x_mean=round(df["x"].mean(), 4), y_std=round(df["y"].std(), 4)
    )

    slope = 0.0
    loss = mse(df, slope)
    for epoch in range(cfg.model.epochs):
        t0 = time.perf_counter()

        slope -= cfg.model.lr * gradient(df, slope)
        new_loss = mse(df, slope)

        if new_loss > loss:
            log.warning("loss_increased", epoch=epoch, lr=cfg.model.lr, loss=round(new_loss, 4))
        loss = new_loss

        log.info(
            "epoch_done",
            epoch=epoch,
            loss=round(loss, 4),
            slope=round(slope, 4),
            elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

        if cfg.demo.fail_at_epoch == epoch:
            try:
                raise RuntimeError(f"simulated failure at epoch {epoch}")
            except RuntimeError:
                log.exception("failed_step", epoch=epoch)
                return

    log.info(
        "done", slope=round(slope, 4), true_slope=cfg.data.true_slope, final_loss=round(loss, 4)
    )


if __name__ == "__main__":
    main()
