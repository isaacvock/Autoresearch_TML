# Six-Channel RNA Training Configuration

Use this reference when editing the root `example_train_config.json` for RNA inputs with six channels. Set `model.name` to exactly one of:

- `small_cnn`
- `saluki_exact`
- `saluki_cnn_hybrid`
- `convolution_universe`

Parameters omitted from `model.params` use the selected model's defaults. Keep all input-channel settings at `6` and scalar output settings at `1`.

## `small_cnn`

A compact, fast CNN baseline with global maximum and mean pooling and an MLP regression head.

```json
"model": {
  "name": "small_cnn",
  "params": {
    "in_ch": 6,
    "n_filters": 64,
    "kernel_size": 9,
    "n_layers": 2,
    "dropout": 0.1,
    "head_hidden": 64,
    "output_dim": 1
  }
}
```

| Parameter | Default | Description |
| --- | ---: | --- |
| `in_ch` | `4` | Number of input channels; override this to `6` for the RNA input. |
| `n_filters` | `64` | Number of feature channels produced by every convolutional layer. |
| `kernel_size` | `9` | Width, in sequence positions, of each one-dimensional convolution. |
| `n_layers` | `2` | Number of convolution, normalization, activation, and dropout blocks. |
| `dropout` | `0.1` | Fraction of activations randomly removed during training in the encoder and head. |
| `head_hidden` | `64` | Width of the hidden layer in the regression head. |
| `output_dim` | `1` | Number of model outputs; keep this at `1` for scalar prediction. |

Use this model for quick experiments or as a simple non-recurrent baseline.

## `saluki_exact`

A close reproduction of the Saluki architecture, consisting of a convolutional tower, reversed GRU, and Saluki-style regression head.

```json
"model": {
  "name": "saluki_exact",
  "params": {
    "seq_depth": 6,
    "filters": 64,
    "kernel_size": 5,
    "num_layers": 6,
    "pooling": "max",
    "dropout": 0.3,
    "augment_shift": 3,
    "ln_epsilon": 0.007,
    "keras_bn_momentum": 0.9,
    "bn_eps": 0.001
  }
}
```

| Parameter | Default | Description |
| --- | ---: | --- |
| `seq_depth` | `6` | Number of input channels; keep this at `6`. |
| `filters` | `64` | Shared width of the convolutional tower, GRU, and hidden head layer. |
| `kernel_size` | `5` | Width, in sequence positions, of the initial and repeated convolutions. |
| `num_layers` | `6` | Number of convolution, dropout, and pooling blocks after the initial convolution. |
| `pooling` | `"max"` | Downsampling operation in each block; accepted values are `"max"` and `"average"`. |
| `dropout` | `0.3` | Fraction of activations randomly removed in convolutional blocks and the dense head. |
| `augment_shift` | `3` | Maximum random right shift applied during training; set it to `0` to disable shift augmentation. |
| `ln_epsilon` | `0.007` | Numerical stabilizer used by channel-wise layer normalization. |
| `keras_bn_momentum` | `0.9` | Batch-normalization momentum expressed using the Keras convention reproduced by this model. |
| `bn_eps` | `0.001` | Numerical stabilizer used by the normalization layers in the regression head. |

The top-level `head_layernorm` training option replaces the two head BatchNorm layers with per-example LayerNorm when set to `true`; it is supported only by `saluki_exact`.

Use this model for standard Saluki training or architecture reproduction.

## `saluki_cnn_hybrid`

Runs exact Saluki and SmallCNN feature encoders in parallel and combines their embeddings in a shared regression head.

```json
"model": {
  "name": "saluki_cnn_hybrid",
  "params": {
    "saluki": {
      "seq_depth": 6
    },
    "cnn": {
      "in_ch": 6
    },
    "fusion": {
      "mode": "concat",
      "output_dim": 1
    }
  }
}
```

Values omitted from any nested section retain that section's defaults. `saluki.seq_depth` and `cnn.in_ch` must match.

### `saluki` parameters

| Parameter | Default | Description |
| --- | ---: | --- |
| `seq_depth` | `6` | Number of input channels consumed by the Saluki branch. |
| `filters` | `64` | Width of the Saluki convolutional stack and GRU embedding. |
| `kernel_size` | `5` | Width of the Saluki branch's one-dimensional convolutions. |
| `num_layers` | `6` | Number of convolution and pooling blocks in the Saluki branch. |
| `pooling` | `"max"` | Saluki downsampling operation; accepted values are `"max"` and `"average"`. |
| `dropout` | `0.3` | Dropout probability in the Saluki convolutional blocks. |
| `augment_shift` | `3` | Maximum random right shift applied once before both branches during training. |
| `ln_epsilon` | `0.007` | Numerical stabilizer for Saluki branch layer normalization. |

### `cnn` parameters

| Parameter | Default | Description |
| --- | ---: | --- |
| `in_ch` | `6` | Number of input channels consumed by the CNN branch. |
| `n_filters` | `64` | Number of feature channels in every CNN convolutional layer. |
| `kernel_size` | `9` | Width of the CNN branch's one-dimensional convolutions. |
| `n_layers` | `2` | Number of convolutional blocks in the CNN branch. |
| `dropout` | `0.1` | Dropout probability in the CNN branch. |

### `fusion` parameters

| Parameter | Default | Description |
| --- | ---: | --- |
| `mode` | `"concat"` | Use `"concat"` for raw branch concatenation or `"project_concat"` to learn separate branch projections first. |
| `saluki_projection_dim` | `64` | Output width of the Saluki projection when `mode` is `"project_concat"`. |
| `cnn_projection_dim` | `64` | Output width of the CNN projection when `mode` is `"project_concat"`. |
| `projection_norm` | `"layer"` | Projection normalization; accepted values are `"none"`, `"batch"`, and `"layer"`. |
| `projection_activation` | `"gelu"` | Projection activation; accepted values are `"none"`, `"relu"`, `"gelu"`, and `"silu"`. |
| `projection_dropout` | `0.0` | Dropout probability applied after each branch projection. |
| `head_hidden` | `64` | Width of the hidden layer in the fused regression head. |
| `head_norm` | `"batch"` | Head normalization; accepted values are `"none"`, `"batch"`, and `"layer"`. |
| `head_activation` | `"relu"` | Head activation; accepted values are `"relu"`, `"gelu"`, and `"silu"`. |
| `head_dropout` | `0.3` | Dropout probability in the fused regression head. |
| `head_norm_eps` | `0.001` | Numerical stabilizer used by projection and head normalization. |
| `head_bn_momentum` | `0.1` | PyTorch-style momentum used when projection or head normalization is BatchNorm. |
| `output_dim` | `1` | Number of model outputs; keep this at `1` for scalar prediction. |
| `weight_init` | `"saluki"` | Initialization for projections and the fused head; use `"saluki"` or `"pytorch"`. |

Use this model when both recurrent Saluki features and globally pooled CNN features may be useful.

## `convolution_universe`

A configurable model for CNN, residual, recurrent, pooling, and Saluki-style architecture experiments. Its default configuration is a six-channel residual dilated CNN without a recurrent layer.

```json
"model": {
  "name": "convolution_universe",
  "params": {
    "in_ch": 6,
    "output_dim": 1
  }
}
```

The fields `filters`, `kernel_size`, `dilations`, `pooling`, and `pool_size` may each be a single value applied to every layer or a list containing exactly `num_layers` values.

### Input and stem

| Parameter | Default | Description |
| --- | ---: | --- |
| `in_ch` | `6` | Number of input channels; keep this at `6`. |
| `output_dim` | `1` | Number of outputs; keep this at `1` for scalar prediction. |
| `augment_shift` | `0` | Maximum random right shift during training; `0` disables it. |
| `weight_init` | `"pytorch"` | Parameter initialization scheme; accepted values are `"pytorch"` and `"saluki"`. |
| `filters` | `64` | Output width of each tower layer, specified as one integer or one integer per layer. |
| `num_layers` | `6` | Number of convolutional tower blocks. |
| `stem_kernel_size` | `11` | Kernel width of the initial convolution before the tower. |
| `stem_padding` | `"same"` | Stem padding policy; `"same"` preserves length and `"valid"` reduces it. |
| `stem_bias` | `true` | Whether the initial convolution includes a learnable bias. |

### Convolutional tower

| Parameter | Default | Description |
| --- | ---: | --- |
| `block_type` | `"conv"` | Tower block implementation; accepted values are `"conv"` and `"convnext"`. |
| `kernel_size` | `7` | Tower convolution width, specified once or separately for every layer. |
| `dilations` | `[1,2,4,8,16,32]` | Spacing between kernel positions, specified once or separately for every layer. |
| `padding` | `"same"` | Tower padding policy; residual connections require `"same"`. |
| `conv_bias` | `true` | Whether standard tower convolutions include a learnable bias. |
| `norm` | `"layer"` | Tower normalization; accepted values are `"none"`, `"batch"`, and `"layer"`. |
| `norm_position` | `"post"` | Apply normalization before (`"pre"`) or after (`"post"`) each standard convolution. |
| `norm_eps` | `1e-5` | Numerical stabilizer used by tower and pre-recurrent normalization. |
| `activation` | `"gelu"` | Tower activation; accepted values are `"relu"`, `"gelu"`, and `"silu"`. |
| `dropout` | `0.1` | Dropout probability in the convolutional tower. |
| `use_residual` | `true` | Whether tower blocks add their input through residual connections. |
| `pooling` | `"none"` | Per-layer pooling operation; accepted values are `"none"`, `"max"`, `"avg"`, and `"average"`. |
| `pool_size` | `2` | Pooling width and stride, specified once or separately for every layer. |

### ConvNeXt-specific controls

| Parameter | Default | Description |
| --- | ---: | --- |
| `mlp_ratio` | `4` | Expansion ratio of the pointwise MLP inside each ConvNeXt block. |
| `layer_scale_init` | `1e-6` | Initial ConvNeXt LayerScale value; use `null` to disable LayerScale. |
| `drop_path_rate` | `0.0` | Maximum stochastic-depth probability across ConvNeXt blocks. |

### Recurrent encoder

| Parameter | Default | Description |
| --- | ---: | --- |
| `pre_rnn_norm` | `"none"` | Normalization before the recurrent layer; use `"none"`, `"batch"`, or `"layer"`. |
| `pre_rnn_activation` | `"none"` | Activation before the recurrent layer; use `"none"`, `"relu"`, `"gelu"`, or `"silu"`. |
| `rnn_type` | `"none"` | Recurrent encoder type; accepted values are `"none"`, `"gru"`, and `"lstm"`. |
| `rnn_hidden` | `128` | Hidden-state width of each recurrent direction. |
| `rnn_layers` | `1` | Number of stacked recurrent layers. |
| `rnn_bidirectional` | `false` | Whether the recurrent encoder reads the sequence in both directions. |
| `rnn_reverse` | `false` | Whether sequence positions are reversed before recurrent processing. |
| `rnn_summary` | `"last"` | Recurrent readout method; use `"last"`, `"mean"`, or `"max"`. |
| `rnn_dropout` | `0.0` | Dropout between recurrent layers; it has an effect only when `rnn_layers` exceeds one. |

### CNN-only readout and prediction head

| Parameter | Default | Description |
| --- | ---: | --- |
| `global_pool` | `"avgmax"` | CNN-only readout using average, maximum, or concatenated average-plus-maximum pooling. |
| `global_pool_size` | `1` | Number of adaptive pooled positions retained by each pooling branch. |
| `head_type` | `"mlp"` | Use `"linear"` for a direct output layer or `"mlp"` for a configurable hidden head. |
| `head_hidden` | `64` | MLP hidden width; it may also be a list of widths or `null` for no hidden layers. |
| `head_norm` | `"layer"` | Hidden-head normalization; accepted values are `"none"`, `"batch"`, and `"layer"`. |
| `head_norm_position` | `"post"` | Apply head normalization before (`"pre"`) or after (`"post"`) each hidden linear layer. |
| `head_activation` | `"gelu"` | Head activation; accepted values are `"relu"`, `"gelu"`, and `"silu"`. |
| `head_dropout` | `0.1` | Dropout probability in the prediction head. |
| `head_norm_eps` | `1e-5` | Numerical stabilizer used by head normalization. |
| `head_bn_momentum` | `0.1` | PyTorch-style momentum used when head normalization is BatchNorm. |

When `rnn_type` is not `"none"`, the recurrent summary supplies the head input and the `global_pool` settings are not used.

Use this model when architecture components themselves are experimental variables.

# General Training Configuration

A typical configuration has the following overall structure:

```json
{
  "dataset": "SCRIPT_OVERWRITES_THIS_FROM_DATASET_DIR",
  "output_dir": "SCRIPT_OVERWRITES_THIS_OUTPUT_DIR",
  "model": {
    "name": "saluki_exact",
    "params": {
      "seq_depth": 6
    }
  },
  "batch_size": 64,
  "epochs": 250,
  "learning_rate": 0.0001,
  "weight_decay": 0.0,
  "gradient_clip_norm": 0.5,
  "patience": 10,
  "monitor": ["val_loss", "val_pearson"],
  "loss": {
    "name": "mse"
  },
  "device": "auto",
  "num_workers": 0,
  "mmap_mode": "r",
  "seed": 42,
  "progress": true,
  "debug_epoch_predictions": false,
  "head_layernorm": false,
  "split_source": "auto"
}
```

The supplied training scripts overwrite `dataset` and `output_dir` when generating a run-specific configuration.

| Field | Default | Description |
| --- | ---: | --- |
| `dataset` | required | Path to the dataset bundle containing the encoded input and associated files. |
| `output_dir` | required | Directory in which checkpoints, metrics, predictions, and run metadata are written. |
| `model` | required here | Selected model name and any constructor parameters that override its defaults. |
| `batch_size` | `64` | Number of examples in each training or evaluation batch. |
| `epochs` | `20` | Maximum number of epochs before training stops. |
| `learning_rate` | `0.001` | AdamW optimizer learning rate. |
| `weight_decay` | `0.0` | AdamW weight-decay coefficient. |
| `gradient_clip_norm` | `0.5` | Maximum global gradient norm; use `null`, `0`, or a negative value to disable clipping. |
| `patience` | `5` | Consecutive non-improving epochs allowed before early stopping; a negative value disables early stopping. |
| `monitor` | `"val_loss"` | Metric or list of metrics used for early stopping and `best.pt` selection. |
| `loss` | `{"name":"mse"}` | Training objective; use `"mse"`, `"weighted_mse"`, or `"binomial_nll"` as appropriate for the dataset. |
| `device` | `"cpu"` | PyTorch device; `"auto"` selects CUDA when available and CPU otherwise. |
| `num_workers` | `0` | Number of subprocesses used by each data loader. |
| `mmap_mode` | `"r"` | NumPy memory-map mode; use `"r"` to avoid loading the full array into memory or `null` to load normally. |
| `seed` | `123` | Seed applied to Python, NumPy, PyTorch, and config-defined random splitting. |
| `progress` | `true` | Whether to print data-loading, batch, epoch, and evaluation progress. |
| `debug_epoch_predictions` | `false` | Whether to save deterministic train and validation predictions after every epoch. |
| `head_layernorm` | `false` | Whether `saluki_exact` uses LayerNorm instead of BatchNorm in its head; other models require `false`. |
| `sequence_controls` | `null` | Optional sequence-ablation operations applied before selecting dataset splits. |
| `split_source` | `"auto"` | Use `"auto"`, `"bundle"`, or `"config"` to choose where train, validation, and test assignments come from. |
| `split` | random 80/10/10 | Split construction settings used when `split_source` selects the configuration. |
| `cv_plan` | `null` | Path to a saved chromosome cross-validation plan; it must be supplied together with `fold`. |
| `fold` | `null` | Zero-based test-fold index for `cv_plan`; the following fold is used for validation. |

Valid scalar-training monitor metrics are:

- `train_loss`
- `train_pearson`
- `val_loss`
- `val_pearson`

When `monitor` is a list, an epoch counts as improved if any listed metric improves.
