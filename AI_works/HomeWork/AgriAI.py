import torch
import pandas as pd
from torch import nn
from timeit import default_timer as timer
word=['StnPres','StnPresMax','StnPresMin','Temperature','RH','Precp','Tc']
df=pd.read_csv('module_class/train_14d.csv')
df_y=df['label']
df_x_train=[]
for i in range(len(word)):
    df_x=df[[word[i],word[i]+'.1',word[i]+'.2',word[i]+'.3',word[i]+'.4',word[i]+'.5',word[i]+'.6',word[i]+'.7',word[i]+'.8',word[i]+'.9',word[i]+'.10',word[i]+'.11',word[i]+'.12',word[i]+'.13']]
    df_x_train.append(torch.tensor(df_x.values, dtype=torch.float32))
df_x_train = torch.stack(df_x_train)
df_x_train = df_x_train.permute(1,0,2)
df_x_train = df_x_train.reshape(2368,-1)
df_y_train = torch.tensor(df_y.values, dtype=torch.float32)
df=pd.read_csv('module_class/test_14d.csv')
df_y=df['label']
df_x_test=[]
for i in range(len(word)):
    df_x=df[[word[i],word[i]+'.1',word[i]+'.2',word[i]+'.3',word[i]+'.4',word[i]+'.5',word[i]+'.6',word[i]+'.7',word[i]+'.8',word[i]+'.9',word[i]+'.10',word[i]+'.11',word[i]+'.12',word[i]+'.13']]
    df_x_test.append(torch.tensor(df_x.values, dtype=torch.float32))
df_x_test = torch.stack(df_x_test)
df_x_test = df_x_test.permute(1,0,2)
df_x_test = df_x_test.reshape(1183,-1)
df_y_test = torch.tensor(df_y.values, dtype=torch.float32)
class Agri(nn.Module):
    def __init__(self):
        super().__init__()
        self.layer_1 = nn.Linear(in_features=98,out_features=13) #輸入一堆x
        self.layer_2 = nn.Linear(in_features=13,out_features=1)
        self.relu = nn.ReLU()
    def forward(self,x):
      return self.layer_2(self.relu(self.layer_1(x)))
model_0 = Agri()
loss_fn=nn.BCEWithLogitsLoss()
optimizer=torch.optim.SGD(params=model_0.parameters(),lr=0.1)
def acc_fn(y_true,y_pred):
    correct=torch.eq(y_true,y_pred).sum().item()
    acc=(correct/len(y_pred)) #val: 0-1
    return acc
print("start training...")
start_time=timer()
Final_acc=0
torch.manual_seed(40)
epochs=2000
for epoch in range(epochs):
    #model train
    model_0.train()
    #forward pass
    y_logits = model_0(df_x_train).squeeze()
    y_preds = torch.round(torch.sigmoid(y_logits))
    #Calculate Loss
    loss = loss_fn(y_logits,df_y_train)
    acc = acc_fn(y_true=df_y_train,y_pred=y_preds)
    #optimizer zero grad
    optimizer.zero_grad()
    #Loss Backward
    loss.backward()
    #optimizer step
    optimizer.step()
    model_0.eval()
    with torch.inference_mode():
        #forward pass
        test_logits = model_0(df_x_test).squeeze()
        test_preds = torch.round(torch.sigmoid(test_logits))
        #calculate loss
        test_loss = loss_fn(test_logits,df_y_test)
        test_acc = acc_fn(y_true=df_y_test,y_pred=test_preds)
        #show
    if epoch%40==0 or epoch==epochs-1:
        print(f"epoch: {epoch} || training loss: {loss:.3f} || training acc: {acc:.2f} || test loss: {test_loss:.3f} || test acc: {test_acc:.2f}")
    final_test_acc=test_acc
end_time=timer()
print(f"學號: 0000000000, 姓名: XXX, training time: {(end_time-start_time):.5f} sec, Final Test Accuracy: {final_test_acc:.5f}")
#為防範個資問題, 學號姓名等資訊已被刪除