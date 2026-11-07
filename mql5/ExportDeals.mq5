//+------------------------------------------------------------------+
//| ExportDeals.mq5                                                  |
//| Export closing deals to CSV for `python -m tiktok_video recap`.  |
//| Output: MQL5/Files/<InpFileName>  (Common folder if InpCommon)   |
//+------------------------------------------------------------------+
#property script_show_inputs

input int      InpDaysBack  = 1;              // Days back (0 = today since 00:00)
input string   InpSymbol    = "XAUUSD";       // Symbol filter ("" = all)
input long     InpMagic     = -1;             // Magic filter (-1 = all)
input string   InpFileName  = "deals.csv";    // File name
input bool     InpCommon    = false;          // Write to Common\Files

void OnStart()
  {
   datetime to   = TimeCurrent();
   datetime from = iTime(_Symbol, PERIOD_D1, 0) - (datetime)InpDaysBack * 86400;
   if(from <= 0)
      from = to - (datetime)MathMax(InpDaysBack, 1) * 86400;

   if(!HistorySelect(from, to))
     {
      PrintFormat("HistorySelect failed: %d", GetLastError());
      return;
     }

   int flags = FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpCommon)
      flags |= FILE_COMMON;
   int h = FileOpen(InpFileName, flags, ',');
   if(h == INVALID_HANDLE)
     {
      PrintFormat("FileOpen failed: %d", GetLastError());
      return;
     }
   FileWrite(h, "time", "symbol", "type", "entry", "volume", "price",
             "profit", "commission", "swap", "magic", "ticket");

   int total = HistoryDealsTotal(), n = 0;

   // Many brokers charge commission on the IN deal. Collect it per position and
   // attribute it to the first closing deal so net P/L per trade is correct.
   long   posIds[];
   double posComm[];
   ArrayResize(posIds, 0);
   ArrayResize(posComm, 0);
   for(int i = 0; i < total; i++)
     {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0 || HistoryDealGetInteger(tk, DEAL_ENTRY) != DEAL_ENTRY_IN)
         continue;
      int k = ArraySize(posIds);
      ArrayResize(posIds, k + 1);
      ArrayResize(posComm, k + 1);
      posIds[k]  = HistoryDealGetInteger(tk, DEAL_POSITION_ID);
      posComm[k] = HistoryDealGetDouble(tk, DEAL_COMMISSION);
     }

   for(int i = 0; i < total; i++)
     {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0)
         continue;
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(tk, DEAL_ENTRY);
      // only realised P/L: OUT, INOUT (reverse), OUT_BY (close by)
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT && entry != DEAL_ENTRY_OUT_BY)
         continue;
      ENUM_DEAL_TYPE type = (ENUM_DEAL_TYPE)HistoryDealGetInteger(tk, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL)
         continue;
      string sym = HistoryDealGetString(tk, DEAL_SYMBOL);
      if(InpSymbol != "" && StringFind(sym, InpSymbol) != 0)   // handles suffix e.g. XAUUSDm
         continue;
      long magic = HistoryDealGetInteger(tk, DEAL_MAGIC);
      if(InpMagic >= 0 && magic != InpMagic)
         continue;

      double comm = HistoryDealGetDouble(tk, DEAL_COMMISSION);
      long   pos  = HistoryDealGetInteger(tk, DEAL_POSITION_ID);
      for(int k = 0; k < ArraySize(posIds); k++)
         if(posIds[k] == pos)
           {
            comm += posComm[k];
            posComm[k] = 0.0;   // only once per position (partial closes)
           }

      // closing deal type is opposite of the position: SELL closes a BUY
      string side = (type == DEAL_TYPE_SELL) ? "buy" : "sell";
      int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      FileWrite(h,
                TimeToString((datetime)HistoryDealGetInteger(tk, DEAL_TIME), TIME_DATE | TIME_SECONDS),
                sym, side, "out",
                DoubleToString(HistoryDealGetDouble(tk, DEAL_VOLUME), 2),
                DoubleToString(HistoryDealGetDouble(tk, DEAL_PRICE), digits),
                DoubleToString(HistoryDealGetDouble(tk, DEAL_PROFIT), 2),
                DoubleToString(comm, 2),
                DoubleToString(HistoryDealGetDouble(tk, DEAL_SWAP), 2),
                IntegerToString(magic), IntegerToString((long)tk));
      n++;
     }
   FileClose(h);
   PrintFormat("Exported %d closing deals -> %s", n, InpFileName);
  }
//+------------------------------------------------------------------+
