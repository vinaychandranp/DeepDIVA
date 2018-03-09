"""
This file is the template for the boilerplate of train/test of a DNN on a points cloud dataset
In particular, point_cloud is designed to work with clouds of bi-dimensional points.

There are a lot of parameter which can be specified to modify the behaviour
and they should be used instead of hard-coding stuff.

@authors: Vinaychandran Pondenkandath , Michele Alberti
"""

import logging

import numpy as np
# Torch
import torch
from torch import nn

# DeepDIVA
import models
# Delegated
from template.runner.standard import Standard, evaluate, train
from template.setup import set_up_model, set_up_dataloaders
from util.misc import checkpoint, adjust_learning_rate
from util.visualization.decision_boundaries import plot_decision_boundaries


#######################################################################################################################
def evaluate_and_plot_decision_boundary(model, val_coords, coords, grid_resolution, val_loader, num_classes, writer,
                                        epoch, no_cuda, epochs, **kwargs):
    min_x, min_y = np.min(val_coords[:, 0]), np.min(val_coords[:, 1])
    max_x, max_y = np.max(val_coords[:, 0]), np.max(val_coords[:, 1])

    grid_x = np.linspace(min_x, max_x, grid_resolution)
    grid_y = np.linspace(min_y, max_y, grid_resolution)

    grid_x, grid_y = np.meshgrid(grid_x, grid_y)

    sm = nn.Softmax()

    if not no_cuda:
        outputs = model(coords)
        outputs = sm(outputs)
        outputs = outputs.data.cpu().numpy()
    else:
        outputs = sm(model(coords)).data.numpy()
    output_winners = np.array([np.argmax(item) for item in outputs])
    outputs_confidence = np.array([outputs[i, item] for i, item in enumerate(output_winners)])

    plot_decision_boundaries(output_winners=output_winners, output_confidence=outputs_confidence,
                             grid_x=grid_x, grid_y=grid_y, point_x=val_coords[:, 0], point_y=val_coords[:, 1],
                             point_class=val_loader.dataset.data[:, 2], num_classes=num_classes,
                             step=epoch, writer=writer, epochs=epochs, **kwargs)
    return


class PointCloud(Standard):
    @staticmethod
    def single_run(writer, log_dir, model_name, epochs, lr, decay_lr, **kwargs):
        """
           This is the main routine where train(), validate() and test() are called.

           Parameters
           ----------
           :param writer: Tensorboard SummaryWriter
               Responsible for writing logs in Tensorboard compatible format.

           :param log_dir: string
               Path to where logs/checkpoints are saved

           :param model_name: string
               Name of the model

           :param epochs: int
               Number of epochs to train

           :param lr: float
               Value for learning rate

           :param decay_lr: boolean
                Decay the lr flag

           :param kwargs: dict
               Any additional arguments.

           :return: train_value, val_value, test_value
               Precision values for train and validation splits. Single precision value for the test split.
       """

        # Get the selected model
        model_expected_input_size = models.__dict__[model_name]().expected_input_size
        logging.info('Model {} expects input size of {}'.format(model_name, model_expected_input_size))

        # Setting up the dataloaders
        train_loader, val_loader, test_loader, num_classes = set_up_dataloaders(model_expected_input_size, **kwargs)

        # Setting up model, optimizer, criterion
        model, criterion, optimizer, best_value, start_epoch = set_up_model(num_classes=num_classes,
                                                                            model_name=model_name,
                                                                            lr=lr,
                                                                            train_loader=train_loader,
                                                                            **kwargs)

        # Core routine
        logging.info('Begin training')
        val_value = np.zeros((epochs - start_epoch))
        train_value = np.zeros((epochs - start_epoch))

        # Make data for points
        grid_resolution = 100
        val_coords = np.squeeze(np.array([input.numpy() for input, target in val_loader]))
        min_x, min_y = np.min(val_coords[:, 0]), np.min(val_coords[:, 1])
        max_x, max_y = np.max(val_coords[:, 0]), np.max(val_coords[:, 1])
        coords = np.array([[x, y]
                           for x in np.linspace(min_x, max_x, grid_resolution)
                           for y in np.linspace(min_y, max_y, grid_resolution)
                           ])
        coords = torch.autograd.Variable(torch.from_numpy(coords).type(torch.FloatTensor))

        if not kwargs['no_cuda']:
            coords = coords.cuda(async=True)

        # PLOT: decision boundary routine
        evaluate_and_plot_decision_boundary(model=model, val_coords=val_coords, coords=coords,
                                            grid_resolution=grid_resolution, val_loader=val_loader,
                                            num_classes=num_classes, writer=writer, epoch=-1, epochs=epochs,
                                            **kwargs)

        PointCloud._validate(val_loader, model, criterion, writer, -1, **kwargs)
        # Add model parameters to Tensorboard
        for name, param in model.named_parameters():
            writer.add_histogram(name, param.clone().cpu().data.numpy(), -1, bins='auto')

        for epoch in range(start_epoch, epochs):
            # Train
            train_value[epoch] = PointCloud._train(train_loader, model, criterion, optimizer, writer, epoch, **kwargs)
            # Validate
            val_value[epoch] = PointCloud._validate(val_loader, model, criterion, writer, epoch, **kwargs)
            if decay_lr is not None:
                adjust_learning_rate(lr, optimizer, epoch, epochs)
            best_value = checkpoint(epoch, val_value[epoch], best_value, model, optimizer, log_dir)

            # PLOT: decision boundary routine
            evaluate_and_plot_decision_boundary(model=model, val_coords=val_coords, coords=coords,
                                                grid_resolution=grid_resolution, val_loader=val_loader,
                                                num_classes=num_classes, writer=writer, epoch=epoch, epochs=epochs,
                                                **kwargs)
            # Add model parameters to Tensorboard
            for name, param in model.named_parameters():
                writer.add_histogram(name, param.clone().cpu().data.numpy(), epoch, bins='auto')

        # Test
        test_value = PointCloud._test(test_loader, model, criterion, writer, epochs, **kwargs)
        logging.info('Training completed')

        return train_value, val_value, test_value

    ####################################################################################################################
    """
    These methods delegate their function to other classes in Standard package. 
    It is useful because sub-classes can selectively change the logic of certain parts only.
    """

    @classmethod
    def _train(cls, train_loader, model, criterion, optimizer, writer, epoch, **kwargs):
        return train.train(train_loader, model, criterion, optimizer, writer, epoch, **kwargs)

    @classmethod
    def _validate(cls, val_loader, model, criterion, writer, epoch, **kwargs):
        return evaluate.validate(val_loader, model, criterion, writer, epoch, **kwargs)

    @classmethod
    def _test(cls, test_loader, model, criterion, writer, epoch, **kwargs):
        return evaluate.test(test_loader, model, criterion, writer, epoch, **kwargs)
