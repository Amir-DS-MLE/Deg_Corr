import csv
import copy
import time
from tqdm import tqdm
import torch
import numpy as np
import os

def train_model(model, criterion, dataloaders, optimizer, metrics, bpath, l='cross_entropy', num_epochs=3, epoch_number=0):
    since = time.time()
    best_model_wts = copy.deepcopy(model.state_dict())
    best_loss = 1e10
    best_spectrum_score = 1
    # Use gpu if available
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model.to(device)
    # Initialize the log file for training and testing loss and metrics
    fieldnames = ['epoch', 'Train_loss', 'Test_loss'] + \
        [f'Train_{m}' for m in metrics.keys()] + \
        [f'Test_{m}' for m in metrics.keys()]
    with open(os.path.join(bpath, 'log_4.csv'), 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

    for epoch in range(1, num_epochs+1):
        print('Epoch {}/{}'.format(epoch, num_epochs))
        print('-' * 10)
        # Each epoch has a training and validation phase
        # Initialize batch summary
        batchsummary = {a: [0] for a in fieldnames}
        torch.cuda.empty_cache()
        for phase in ['Train', 'Test']:
            if phase == 'Train':
                model.train()  # Set model to training mode
            else:
                model.eval()   # Set model to evaluate mode
            
            # Iterate over data.
            for batch in tqdm(iter(dataloaders[phase])):
                # These lines appear to be correct.
                images = batch['image'].to(device)
                true_masks = batch['mask'].to(device, dtype=torch.long)
                true_masks_tensor = batch['mask'].to(device, dtype=torch.float)

                # zero the parameter gradients
                optimizer.zero_grad()

                # track history if only in train
                with torch.set_grad_enabled(phase == 'Train'):
                    # currently giving a tensor of [batch,dimension,dimension,channel]
                    # expects [batch, channel, dim, dim]
                    images = images.permute(0, 3, 1, 2).contiguous()
                    mask_pred = model(images)
                    y_pred_tensor = mask_pred
                    soft = torch.nn.Softmax(dim=1)
                    y_pred_tensor_soft = soft(mask_pred)
                    y_pred_tensor_soft= y_pred_tensor_soft.permute(1,0,2,3).contiguous()

                    # y_pred_tensor = mask_pred['out']
                    pred = torch.argmax(y_pred_tensor, dim=1)
                    
                    # ravel the prediction tensor, works only for batch of 1
                    torch_y_pred_ravel = y_pred_tensor_soft.reshape(y_pred_tensor_soft.shape[0], y_pred_tensor_soft.shape[1], 
                                                               y_pred_tensor_soft.shape[2]*y_pred_tensor_soft.shape[3])
                    
                    torch_y_pred_ravel = torch_y_pred_ravel.reshape(torch_y_pred_ravel.shape[0], 
                                                               torch_y_pred_ravel.shape[1]*torch_y_pred_ravel.shape[2])
                    
                    # predefined tensor that sets up for a weighted average
                    torch_set = torch.tensor([[0],[1],[2],[3]]).to(dtype=torch.float32).to(device)
                    trans_set = torch.transpose(torch_set, 0, 1)
                    torch_spec = torch.matmul(trans_set, torch_y_pred_ravel)

                    if l != 'cross_entropy':
                        y_pred_tensor = torch_spec
                        true_masks_tensor= true_masks_tensor.reshape(true_masks_tensor.shape[0], 
                                                                     true_masks_tensor.shape[1]*true_masks_tensor.shape[2])
                        true_masks_tensor= true_masks_tensor.reshape(1, true_masks_tensor.shape[0]*true_masks_tensor.shape[1])                        
                    y_pred = pred.data.cpu().numpy()
                    # y_pred = mask_pred['out'].data.cpu().numpy()[0]
                    # pred = torch.argmax(y_pred, dim=1)
                    
                    # This is set up perfectly for the use of determining accuracy
                    y_pred = y_pred.ravel()
                    y_true = true_masks.data.cpu().numpy().ravel()
                    
                    if l != 'cross_entropy': 
                        loss = criterion(y_pred_tensor, true_masks_tensor)
                    else:
                        loss = criterion(y_pred_tensor, true_masks)
                            
                    
                    for name, metric in metrics.items():
                        if name == 'f1_score':
                            batchsummary[f'{phase}_{name}'].append(metric(y_true, y_pred, average='weighted'))
                        if name == 'jaccard_score':
                            batchsummary[f'{phase}_{name}'].append(metric(y_true, y_pred, average='weighted'))
                        if name == 'spectrum_score':
                            batchsummary[f'{phase}_{name}'].append(metric(y_true, y_pred))
                        else:
                            batchsummary[f'{phase}_{name}'].append(metric(y_true.astype('uint8'), y_pred, average='weighted'))

                    # backward + optimize only if in training phase
                    if phase == 'Train':
                        loss.backward()
                        optimizer.step()
            batchsummary['epoch'] = epoch
            epoch_loss = loss
            batchsummary[f'{phase}_loss'] = epoch_loss.item()
            print('{} Loss: {:.4f}'.format(phase, loss))
        for field in fieldnames[3:]:
            batchsummary[field] = np.mean(batchsummary[field])
        print(batchsummary)
        with open(os.path.join(bpath, 'log_3.csv'), 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writerow(batchsummary)
            # deep copy the model
            if phase == 'Test' and batchsummary['Test_spectrum_score'] < best_spectrum_score:
                best_spectrum_score = batchsummary['Test_spectrum_score']
                best_model_wts = copy.deepcopy(model.state_dict())
                model.load_state_dict(best_model_wts)
                torch.save(model, os.path.join(bpath, 'weights_'+ str(epoch+epoch_number) + '.pt'))

    time_elapsed = time.time() - since
    print('Training complete in {:.0f}m {:.0f}s'.format(
        time_elapsed // 60, time_elapsed % 60))
    print('Lowest Loss: {:4f}'.format(best_loss))

    # load best model weights
    model.load_state_dict(best_model_wts)
    return model
